"""The synchronous half of discovery: one search, every source at once, one response.

The poller is patient and thorough; this is neither. It fans out with a hard per-target timeout
(aggregators 8s, watchlist boards 30s), caps each source, and never lets one vendor's outage fail
the request -- the user typed a query and is watching a spinner.

Two rules differ from the poller on purpose:

* An identity-hash match returns the job the user already has, rather than inserting a repost.
  The poller is recording history (a genuinely re-posted job is a new event); a search box is
  answering "what is out there", and showing the same role twice -- once scored, once not --
  is just wrong.
* Nothing is scored here. Scoring needs the embedding provider and takes long enough to blow the
  request budget, so the caller enqueues `score_jobs` and the client refetches.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories.jobs import POSTED_WITHIN_DAYS
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.errors import RateLimited
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.quota import (
    GENERIC_WORDING,
    QuotaState,
    QuotaStore,
    describe,
    guarded_search,
)
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES, get_aggregator, get_source
from rhapto.services.discovery.sources.base import SourceError

logger = logging.getLogger(__name__)

#: How long an aggregator gets before the response goes out without it.
LIVE_TIMEOUT_SECONDS = 8.0
#: How long a watchlist board gets. Boards are downloaded live and some are big (hundreds of
#: postings parsed off the loop in chunks), so they get a longer budget than the aggregators.
BOARD_TIMEOUT_SECONDS = 30.0
#: How many postings per source reach the database. The grid shows a page at a time; a search
#: box that quietly ingests hundreds of rows per keystroke is a different product.
LIVE_CAP = 30
#: `SourceOutcome.error` is one line for the UI; a pile of board failures is cut here.
ERROR_CAP = 300

OutcomeKind = Literal["ok", "failed", "rate_limited", "unavailable", "quota_exhausted"]
OutcomeState = Literal["ok", "partial", "failed", "rate_limited", "unavailable", "quota_exhausted"]
#: Kinds that name the whole source's state when every one of its targets reports the same one.
_UNIFORM_KINDS: tuple[str, ...] = ("rate_limited", "quota_exhausted", "unavailable")


@dataclass(frozen=True)
class LiveTarget:
    """One thing to ask: an aggregator (board None) or a watchlist board."""

    source: str
    board: str | None = None
    company: str | None = None
    credentials: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BoardFailure:
    """One target that did not answer. `name` is what the user knows it by."""

    name: str
    kind: OutcomeKind
    message: str


@dataclass
class FetchResult:
    target: LiveTarget
    postings: list[Posting]
    kind: OutcomeKind = "ok"
    message: str | None = None
    quota: QuotaState | None = None


@dataclass
class SourceOutcome:
    found: int = 0
    new: int = 0
    boards_ok: int = 0
    failures: list[BoardFailure] = field(default_factory=list)
    state: OutcomeState = "ok"
    #: Kept for old clients: set only when the whole source failed (never for a partial result).
    error: str | None = None
    quota: QuotaState | None = None


@dataclass
class LiveResult:
    jobs: list[Job]
    per_source: dict[str, SourceOutcome]
    new_job_ids: list[uuid.UUID]


def _target_name(target: LiveTarget) -> str:
    return target.company or target.board or target.source


async def _fetch_one(
    http: DiscoveryHttp | FakeDiscoveryHttp,
    target: LiveTarget,
    spec: SearchSpec,
    timeout: float,
    board_timeout: float,
    quota_store: QuotaStore | None,
) -> FetchResult:
    """Fetch one target. Never raises, never touches the session.

    The session is deliberately out of reach here: these coroutines run concurrently under
    `asyncio.gather`, and an AsyncSession is not safe to share between them.
    """
    budget = board_timeout if target.board is not None else timeout
    cls = SOURCES.get(target.source)
    info = cls.info if cls is not None else None
    if info is not None and info.unavailable is not None:
        # Even an existing user's enabled row never reaches the vendor: no call, no bypass.
        return FetchResult(target, [], "unavailable", info.unavailable)
    try:
        # Source.fetch/fetch_search are typed against the concrete DiscoveryHttp for production
        # callers; FakeDiscoveryHttp implements the same get_json/get_text/aclose surface used by
        # every adapter, so this narrowing is safe for the test double too (same pattern as the
        # poller).
        real_http = cast("DiscoveryHttp", http)
        if target.board is not None:
            postings = await asyncio.wait_for(
                get_source(target.source).fetch(
                    real_http, board=target.board, keywords=list(spec.keywords)
                ),
                budget,
            )
            return FetchResult(target, postings)
        if info is not None and info.live_only:
            guarded = await asyncio.wait_for(
                guarded_search(quota_store, target.source, real_http, spec, target.credentials),
                budget,
            )
            if guarded.skipped:
                return FetchResult(
                    target, [], "quota_exhausted", describe(guarded.state), guarded.state
                )
            if guarded.rate_limited:
                # A 429 that carried a reset time reads like an exhausted quota (spec 5.6);
                # without one it is the generic rate-limit wording.
                reset_known = guarded.state is not None and guarded.state.reset_at is not None
                return FetchResult(
                    target,
                    [],
                    "quota_exhausted" if reset_known else "rate_limited",
                    describe(guarded.state),
                    guarded.state,
                )
            return FetchResult(target, guarded.postings, quota=guarded.state)
        postings = await asyncio.wait_for(
            get_aggregator(target.source).fetch_search(real_http, spec, target.credentials),
            budget,
        )
    except TimeoutError:
        return FetchResult(target, [], "failed", f"timed out after {budget:g}s")
    except RateLimited:
        return FetchResult(target, [], "rate_limited", GENERIC_WORDING)
    except SourceError as exc:
        return FetchResult(target, [], "failed", str(exc))
    except Exception as exc:  # one adapter's bug must not fail the search
        logger.exception("live search of %s failed", target.source)
        return FetchResult(target, [], "failed", f"{type(exc).__name__}: {exc}")
    return FetchResult(target, postings)


def _finish(outcome: SourceOutcome) -> None:
    """Decide the source's state and its single legacy `error` line from the collected failures."""
    failures = outcome.failures
    if not failures:
        outcome.state = "ok"
        return
    if outcome.boards_ok > 0:
        outcome.state = "partial"  # jobs are shown; the failures are reported beside them
        return
    kinds = {f.kind for f in failures}
    only = next(iter(kinds)) if len(kinds) == 1 else None
    outcome.state = cast("OutcomeState", only) if only in _UNIFORM_KINDS else "failed"
    if len(failures) == 1:
        outcome.error = failures[0].message
    else:
        joined = "; ".join(f"{f.name} {f.message}" for f in failures)
        outcome.error = f"{len(failures)} boards failed: {joined}"[:ERROR_CAP]


def _within_window(posting: Posting, posted_within: str) -> bool:
    """A posting with no date from the source is kept: silence is not evidence of age."""
    days = POSTED_WITHIN_DAYS.get(posted_within)
    if days is None or posting.posted_at is None:
        return True
    return posting.posted_at >= datetime.now(UTC) - timedelta(days=days)


async def live_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    http: DiscoveryHttp | FakeDiscoveryHttp,
    spec: SearchSpec,
    targets: list[LiveTarget],
    timeout: float = LIVE_TIMEOUT_SECONDS,
    board_timeout: float = BOARD_TIMEOUT_SECONDS,
    quota_store: QuotaStore | None = None,
    cap: int = LIVE_CAP,
) -> LiveResult:
    """Ask every target at once, ingest what came back, and report per source.

    `quota_store=None` means no quota guard (a live-only source is then called unguarded).
    """
    per_source: dict[str, SourceOutcome] = {}
    if not targets:
        return LiveResult(jobs=[], per_source=per_source, new_job_ids=[])
    fetched = await asyncio.gather(
        *(_fetch_one(http, target, spec, timeout, board_timeout, quota_store) for target in targets)
    )

    jobs: list[Job] = []
    new_ids: list[uuid.UUID] = []
    seen_hashes: set[str] = set()
    seen_ids: set[uuid.UUID] = set()
    # Ingest is sequential and after the gather: one session, one writer.
    for result in fetched:
        target = result.target
        outcome = per_source.setdefault(target.source, SourceOutcome())
        if result.quota is not None:
            outcome.quota = result.quota
        if result.kind != "ok":
            outcome.failures.append(
                BoardFailure(_target_name(target), result.kind, result.message or "")
            )
            continue
        outcome.boards_ok += 1
        kept = [p for p in result.postings if _within_window(p, spec.posted_within)][:cap]
        outcome.found += len(kept)
        for posting in kept:
            company = target.company or posting.company
            text_hash = dedupe_hash(posting.jd_text)
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            existing = await jobs_repo.find_by_external_id(
                session, user_id, target.source, posting.external_id
            ) or await jobs_repo.find_by_identity(
                session, user_id, identity_hash(company, posting.title, posting.location)
            )
            if existing is not None:
                if existing.id not in seen_ids:
                    seen_ids.add(existing.id)
                    jobs.append(existing)
                continue
            job = await jobs_repo.create_discovered_job(
                session,
                user_id,
                source=target.source,
                external_id=posting.external_id,
                company=company,
                title=posting.title,
                location=posting.location,
                url=posting.url,
                jd_text=posting.jd_text,
                posted_at=posting.posted_at,
                identity_hash=identity_hash(company, posting.title, posting.location),
                repost_of=None,
                search_id=None,
                salary_text=posting.salary_text,
            )
            seen_ids.add(job.id)
            jobs.append(job)
            new_ids.append(job.id)
            outcome.new += 1
    for outcome in per_source.values():
        _finish(outcome)
    await session.flush()
    # Scored jobs first, best fit at the top; everything the search just found follows in the
    # order the sources returned it, and gets its ring as soon as the worker catches up.
    jobs.sort(key=lambda j: (j.best_fit is None, -(j.best_fit or 0)))
    return LiveResult(jobs=jobs, per_source=per_source, new_job_ids=new_ids)
