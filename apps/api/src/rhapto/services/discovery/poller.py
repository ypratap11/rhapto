"""One poll: every watchlist board and enabled aggregator -> new scored jobs and a run record each."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories.discovery import PAUSE_AFTER
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.base import SourceError
from rhapto.services.scoring import score_and_store

logger = logging.getLogger(__name__)
PAUSED_MESSAGE = "paused after 3 failures; save the watchlist entry to retry"
StepCallback = Callable[[str], Awaitable[None]]


@dataclass
class SourceSpec:
    source: str
    board: str | None
    company: str | None
    keywords: list[str] = field(default_factory=list)
    entry_updated_at: datetime | None = None


@dataclass
class RunResult:
    source: str
    board: str | None
    found: int
    new: int
    error: str | None


@dataclass
class PollSummary:
    results: list[RunResult]
    new_jobs: int
    new_job_ids: list[uuid.UUID]


async def build_specs(session: AsyncSession, user_id: uuid.UUID) -> list[SourceSpec]:
    specs = [
        SourceSpec(
            source=row.source,
            board=row.board,
            company=row.company,
            keywords=list(row.keywords),
            entry_updated_at=row.updated_at,
        )
        for row in await profile_repo.list_watchlist(session, user_id)
    ]
    track_keywords: list[str] = []
    for track in await profile_repo.list_tracks(session, user_id):
        track_keywords.extend(k for k in track.keywords if k not in track_keywords)
    for agg in await profile_repo.list_aggregators(session, user_id):
        if agg.enabled:
            specs.append(
                SourceSpec(
                    source=agg.source,
                    board=None,
                    company=None,
                    keywords=list(agg.keywords) or track_keywords,
                    entry_updated_at=agg.updated_at,
                )
            )
    return specs


async def _is_paused(session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec) -> bool:
    if spec.entry_updated_at is None:
        # No watchlist/aggregator entry behind this spec (e.g. an explicit CLI/test spec) ->
        # there is nothing a human could "save" to lift a pause, so it is never paused.
        return False
    if (
        await disc_repo.consecutive_failures(session, user_id, spec.source, spec.board)
        < PAUSE_AFTER
    ):
        return False
    runs = await disc_repo.latest_runs(session, user_id)
    last = next((r for r in runs if r.source == spec.source and r.board == spec.board), None)
    if last is None:
        return True
    return spec.entry_updated_at <= last.started_at


async def _ingest(
    session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec, postings: list[Posting]
) -> list[Job]:
    """Dedupe order: external id -> skip; in-batch text-hash repeat -> skip; text hash of an
    EXISTING job (any source) -> insert flagged as a repost of it; else an identity-hash match
    -> insert flagged as a repost of it; else a plain new job. A text-hash match against an
    existing job is never silently dropped -- only a duplicate seen earlier in this same fetch
    is."""
    created: list[Job] = []
    seen_hashes: set[str] = set()
    for posting in postings:
        company = spec.company or posting.company
        if (
            await jobs_repo.find_by_external_id(session, user_id, spec.source, posting.external_id)
            is not None
        ):
            continue
        text_hash = dedupe_hash(posting.jd_text)
        if text_hash in seen_hashes:
            continue
        seen_hashes.add(text_hash)
        ident = identity_hash(company, posting.title, posting.location)
        repost_source = await jobs_repo.find_duplicate(
            session, user_id, text_hash
        ) or await jobs_repo.find_by_identity(session, user_id, ident)
        job = await jobs_repo.create_discovered_job(
            session,
            user_id,
            source=spec.source,
            external_id=posting.external_id,
            company=company,
            title=posting.title,
            location=posting.location,
            url=posting.url,
            jd_text=posting.jd_text,
            posted_at=posting.posted_at,
            identity_hash=ident,
            repost_of=repost_source.id if repost_source else None,
        )
        created.append(job)
    return created


async def poll_sources(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    http: DiscoveryHttp | FakeDiscoveryHttp,
    embedder: EmbeddingProvider,
    specs: list[SourceSpec] | None = None,
    on_step: StepCallback | None = None,
) -> PollSummary:
    async def step(name: str) -> None:
        if on_step is not None:
            await on_step(name)

    specs = specs if specs is not None else await build_specs(session, user_id)
    results: list[RunResult] = []
    new_ids: list[uuid.UUID] = []
    await step("fetch")
    for spec in specs:
        if await _is_paused(session, user_id, spec):
            run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
            disc_repo.finish_run(run, found=0, new=0, error=PAUSED_MESSAGE)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, PAUSED_MESSAGE))
            continue
        run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
        # Commit the run row now, before any risky work, so it survives a rollback below: a
        # failure inside the try (including at commit time) rolls back only the fetch/ingest/
        # score work, never this already-persisted row.
        await session.commit()
        try:
            # Source.fetch is typed against the concrete DiscoveryHttp for production callers;
            # FakeDiscoveryHttp implements the same get_json/get_text/aclose surface used by
            # every adapter, so this narrowing is safe for the test double too.
            postings = await get_source(spec.source).fetch(
                cast(DiscoveryHttp, http), board=spec.board, keywords=spec.keywords
            )
            await step("dedupe")
            created = await _ingest(session, user_id, spec, postings)
            await step("score")
            await score_and_store(session, user_id, created, embedder)
            disc_repo.finish_run(run, found=len(postings), new=len(created), error=None)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, len(postings), len(created), None))
            new_ids.extend(j.id for j in created)
        except SourceError as exc:
            await session.rollback()
            disc_repo.finish_run(run, found=0, new=0, error=str(exc))
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, str(exc)))
        except Exception as exc:  # a bug in one adapter must not take the others down
            logger.exception("poll of %s/%s failed", spec.source, spec.board)
            await session.rollback()
            message = f"{type(exc).__name__}: {exc}"
            disc_repo.finish_run(run, found=0, new=0, error=message)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, message))
    await step("done")
    return PollSummary(results=results, new_jobs=len(new_ids), new_job_ids=new_ids)
