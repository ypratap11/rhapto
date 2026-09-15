"""One poll: every watchlist board and enabled aggregator -> new scored jobs and a run record each."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job, WatchlistEntry
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.db.repositories.discovery import PAUSE_AFTER
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.services.discovery.boards import board_from_url
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import Remote, SearchSpec, derive_searches
from rhapto.services.discovery.sources import SOURCES, get_aggregator, get_source
from rhapto.services.discovery.sources.base import SourceError
from rhapto.services.scoring import score_and_store

logger = logging.getLogger(__name__)
PAUSED_MESSAGE = "paused after 3 failures; save the watchlist entry to retry"
NO_API_KEY_MESSAGE = "no API key"
StepCallback = Callable[[str], Awaitable[None]]


@dataclass
class SourceSpec:
    source: str
    board: str | None
    company: str | None
    keywords: list[str] = field(default_factory=list)
    entry_updated_at: datetime | None = None
    #: Set for aggregator specs driven by a saved search; None for board specs.
    search: SearchSpec | None = None
    search_id: uuid.UUID | None = None
    credentials: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    source: str
    board: str | None
    found: int
    new: int
    error: str | None
    search_id: uuid.UUID | None = None
    unlisted: int = 0


@dataclass
class PollSummary:
    results: list[RunResult]
    new_jobs: int
    new_job_ids: list[uuid.UUID]


async def build_specs(
    session: AsyncSession, user_id: uuid.UUID, *, fernet: Fernet | None = None
) -> list[SourceSpec]:
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
    enabled = [a for a in await profile_repo.list_aggregators(session, user_id) if a.enabled]
    if not enabled:
        return specs
    # A user who has never opened the Searches tab still gets the market: derive on first poll.
    await derive_searches(session, user_id)
    searches = [s for s in await searches_repo.list_searches(session, user_id) if s.active]
    for search in searches:
        for agg in enabled:
            info = SOURCES[agg.source].info if agg.source in SOURCES else None
            credentials: dict[str, str] = {}
            if info is not None and info.needs_key:
                credentials = (
                    await creds_repo.get_credentials(session, fernet, user_id, agg.source)
                    if fernet is not None
                    else {}
                )
            specs.append(
                SourceSpec(
                    source=agg.source,
                    board=None,
                    company=None,
                    keywords=list(search.keywords),
                    entry_updated_at=agg.updated_at,
                    search=SearchSpec(
                        keywords=tuple(search.keywords),
                        location=search.location,
                        remote=cast("Remote", search.remote),
                        name=search.name,
                    ),
                    search_id=search.id,
                    credentials=credentials,
                )
            )
    if not searches:
        # Legacy path: no tracks and no searches, so fall back to the aggregator row's own
        # keywords exactly as before saved searches existed.
        for agg in enabled:
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
    # Only failures after the entry was last saved count, so a save grants three fresh attempts
    # instead of a single retry.
    failures = await disc_repo.consecutive_failures(
        session, user_id, spec.source, spec.board, since=spec.entry_updated_at
    )
    if failures < PAUSE_AFTER:
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
            search_id=spec.search_id,
        )
        created.append(job)
    return created


async def _discover_boards(
    session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec, created: list[Job]
) -> None:
    """Add a watchlist row for every ATS board a new job's URL points at."""
    existing = {
        (row.source, row.board) for row in await profile_repo.list_watchlist(session, user_id)
    }
    for job in created:
        match = board_from_url(job.url or "")
        if match is None or match in existing:
            continue
        existing.add(match)
        session.add(
            WatchlistEntry(
                user_id=user_id,
                company=job.company or match[1],
                source=match[0],
                board=match[1],
                keywords=list(spec.keywords),
                discovered=True,
            )
        )
    await session.flush()


async def poll_sources(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    http: DiscoveryHttp | FakeDiscoveryHttp,
    embedder: EmbeddingProvider,
    specs: list[SourceSpec] | None = None,
    on_step: StepCallback | None = None,
    fernet: Fernet | None = None,
) -> PollSummary:
    async def step(name: str) -> None:
        if on_step is not None:
            await on_step(name)

    specs = specs if specs is not None else await build_specs(session, user_id, fernet=fernet)
    results: list[RunResult] = []
    new_ids: list[uuid.UUID] = []
    await step("fetch")
    for spec in specs:
        if await _is_paused(session, user_id, spec):
            run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
            run.search_id = spec.search_id
            disc_repo.finish_run(run, found=0, new=0, error=PAUSED_MESSAGE)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, PAUSED_MESSAGE, spec.search_id))
            continue
        info = SOURCES[spec.source].info if spec.source in SOURCES else None
        if spec.search is not None and info is not None and info.needs_key and not spec.credentials:
            run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
            run.search_id = spec.search_id
            disc_repo.finish_run(run, found=0, new=0, error=NO_API_KEY_MESSAGE)
            await session.commit()
            results.append(
                RunResult(spec.source, spec.board, 0, 0, NO_API_KEY_MESSAGE, spec.search_id)
            )
            continue
        run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
        run.search_id = spec.search_id
        # Commit the run row now, before any risky work, so it survives a rollback below: a
        # failure inside the try (including at commit time) rolls back only the fetch/ingest/
        # score work, never this already-persisted row.
        await session.commit()
        try:
            # Source.fetch is typed against the concrete DiscoveryHttp for production callers;
            # FakeDiscoveryHttp implements the same get_json/get_text/aclose surface used by
            # every adapter, so this narrowing is safe for the test double too.
            if spec.search is not None:
                postings = await get_aggregator(spec.source).fetch_search(
                    cast("DiscoveryHttp", http), spec.search, spec.credentials
                )
            else:
                postings = await get_source(spec.source).fetch(
                    cast("DiscoveryHttp", http), board=spec.board, keywords=spec.keywords
                )
            await step("dedupe")
            created = await _ingest(session, user_id, spec, postings)
            await _discover_boards(session, user_id, spec, created)
            await step("score")
            await score_and_store(session, user_id, created, embedder)
            disc_repo.finish_run(run, found=len(postings), new=len(created), error=None)
            await session.commit()
            results.append(
                RunResult(
                    spec.source, spec.board, len(postings), len(created), None, spec.search_id
                )
            )
            new_ids.extend(j.id for j in created)
        except SourceError as exc:
            await session.rollback()
            disc_repo.finish_run(run, found=0, new=0, error=str(exc))
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, str(exc), spec.search_id))
        except Exception as exc:  # a bug in one adapter must not take the others down
            logger.exception("poll of %s/%s failed", spec.source, spec.board)
            await session.rollback()
            message = f"{type(exc).__name__}: {exc}"
            disc_repo.finish_run(run, found=0, new=0, error=message)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, message, spec.search_id))
    await step("done")
    return PollSummary(results=results, new_jobs=len(new_ids), new_job_ids=new_ids)
