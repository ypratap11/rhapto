"""The synchronous half of discovery: one search, every source at once, one response.

The poller is patient and thorough; this is neither. It fans out with a hard per-source timeout,
caps each source, and never lets one vendor's outage fail the request -- the user typed a query
and is watching a spinner.

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
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories.jobs import POSTED_WITHIN_DAYS
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import get_aggregator, get_source
from rhapto.services.discovery.sources.base import SourceError

logger = logging.getLogger(__name__)

#: How long any one source gets before the response goes out without it.
LIVE_TIMEOUT_SECONDS = 8.0
#: How many postings per source reach the database. The grid shows a page at a time; a search
#: box that quietly ingests hundreds of rows per keystroke is a different product.
LIVE_CAP = 30


@dataclass(frozen=True)
class LiveTarget:
    """One thing to ask: an aggregator (board None) or a watchlist board."""

    source: str
    board: str | None = None
    company: str | None = None
    credentials: dict[str, str] = field(default_factory=dict)


@dataclass
class SourceOutcome:
    found: int = 0
    new: int = 0
    error: str | None = None


@dataclass
class LiveResult:
    jobs: list[Job]
    per_source: dict[str, SourceOutcome]
    new_job_ids: list[uuid.UUID]


async def _fetch_one(
    http: DiscoveryHttp | FakeDiscoveryHttp,
    target: LiveTarget,
    spec: SearchSpec,
    timeout: float,
) -> tuple[LiveTarget, list[Posting], str | None]:
    """Fetch one target. Never raises, never touches the session.

    The session is deliberately out of reach here: these coroutines run concurrently under
    `asyncio.gather`, and an AsyncSession is not safe to share between them.
    """
    try:
        # Source.fetch/fetch_search are typed against the concrete DiscoveryHttp for production
        # callers; FakeDiscoveryHttp implements the same get_json/get_text/aclose surface used by
        # every adapter, so this narrowing is safe for the test double too (same pattern as the
        # poller).
        if target.board is None:
            postings = await asyncio.wait_for(
                get_aggregator(target.source).fetch_search(
                    cast("DiscoveryHttp", http), spec, target.credentials
                ),
                timeout,
            )
        else:
            postings = await asyncio.wait_for(
                get_source(target.source).fetch(
                    cast("DiscoveryHttp", http), board=target.board, keywords=list(spec.keywords)
                ),
                timeout,
            )
    except TimeoutError:
        return (target, [], f"timed out after {timeout:g}s")
    except SourceError as exc:
        return (target, [], str(exc))
    except Exception as exc:  # one adapter's bug must not fail the search
        logger.exception("live search of %s failed", target.source)
        return (target, [], f"{type(exc).__name__}: {exc}")
    return (target, postings, None)


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
    cap: int = LIVE_CAP,
) -> LiveResult:
    """Ask every target at once, ingest what came back, and report per source."""
    per_source: dict[str, SourceOutcome] = {}
    if not targets:
        return LiveResult(jobs=[], per_source=per_source, new_job_ids=[])
    fetched = await asyncio.gather(*(_fetch_one(http, target, spec, timeout) for target in targets))

    jobs: list[Job] = []
    new_ids: list[uuid.UUID] = []
    seen_hashes: set[str] = set()
    seen_ids: set[uuid.UUID] = set()
    # Ingest is sequential and after the gather: one session, one writer.
    for target, postings, error in fetched:
        outcome = per_source.setdefault(target.source, SourceOutcome())
        if error is not None:
            outcome.error = outcome.error or error
            continue
        kept = [p for p in postings if _within_window(p, spec.posted_within)][:cap]
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
    await session.flush()
    # Scored jobs first, best fit at the top; everything the search just found follows in the
    # order the sources returned it, and gets its ring as soon as the worker catches up.
    jobs.sort(key=lambda j: (j.best_fit is None, -(j.best_fit or 0)))
    return LiveResult(jobs=jobs, per_source=per_source, new_job_ids=new_ids)
