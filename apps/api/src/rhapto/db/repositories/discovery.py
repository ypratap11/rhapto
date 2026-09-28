from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, JobScore, PollRun


async def start_run(
    session: AsyncSession, user_id: uuid.UUID, source: str, board: str | None
) -> PollRun:
    run = PollRun(user_id=user_id, source=source, board=board, started_at=datetime.now(UTC))
    session.add(run)
    await session.flush()
    return run


def finish_run(run: PollRun, *, found: int, new: int, error: str | None) -> None:
    run.found, run.new, run.error = found, new, (error[:4000] if error else None)
    run.finished_at = datetime.now(UTC)


async def latest_runs(session: AsyncSession, user_id: uuid.UUID) -> list[PollRun]:
    """Newest run per (source, board, search_id).

    A board poll always has ``search_id`` NULL, so this is a no-op refinement for boards;
    a keyless aggregator driven by several saved searches shares ``(source, board=None)``
    but not ``search_id``, so each search's own runs now survive here instead of collapsing
    into whichever one happened to start last.
    """
    rows = await session.scalars(
        select(PollRun)
        .where(PollRun.user_id == user_id)
        .order_by(PollRun.source, PollRun.board, PollRun.search_id, PollRun.started_at.desc())
        .distinct(PollRun.source, PollRun.board, PollRun.search_id)
    )
    return sorted(rows, key=lambda r: r.started_at, reverse=True)


@dataclass(frozen=True)
class SearchRunStats:
    """What one saved search's poll history says about it."""

    #: Attempts recorded for this search, across every source it was run against.
    runs: int
    #: The largest `found` any of those attempts returned. 0 means no attempt has ever returned a
    #: posting, which is what "this search has never returned a job" actually means.
    best: int
    last_run_at: datetime | None

    @property
    def ever_found(self) -> bool:
        return self.best > 0


async def search_run_stats(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[uuid.UUID, SearchRunStats]:
    """Per saved search: how many times it has polled, and whether any poll ever found anything.

    Read from `poll_runs`, NOT from `jobs.search_id`, and that choice is the whole point.
    `EXISTS (jobs WHERE search_id = s.id)` is a proxy that lies in three ways: `jobs.search_id` is
    `ON DELETE SET NULL` (`alembic/versions/0006_searches.py`), so deleting a search detaches its
    history; job rows are deletable; and `backfill_public_jobs` deliberately does not copy
    `search_id`. `searches.new_counts` is worse for this purpose -- it counts only jobs newer than
    `last_viewed_at`, so it returns 0 for "never matched" and for "you have seen them all" alike.

    `poll_runs` persists one row per attempt with `found`, and a successful fetch that returned
    nothing is stored as `found = 0, error IS NULL`. That is the only record that can tell "has
    never matched" from "nothing new".

    One grouped statement for every search, not one per row: the dashboard, the Searches tab and
    the Jobs-page diagnosis all want the whole set at once. Searches with no runs are simply absent
    from the mapping -- the caller reads that as `runs = 0`, "has not run yet".
    """
    rows = await session.execute(
        select(
            PollRun.search_id,
            func.count().label("runs"),
            func.max(PollRun.found).label("best"),
            func.max(PollRun.started_at).label("last_run_at"),
        )
        .where(PollRun.user_id == user_id, PollRun.search_id.is_not(None))
        .group_by(PollRun.search_id)
    )
    return {
        search_id: SearchRunStats(runs=int(runs or 0), best=int(best or 0), last_run_at=last_run_at)
        for search_id, runs, best, last_run_at in rows.all()
        if search_id is not None
    }


#: What a search with no `poll_runs` rows at all reads as: never attempted, never found.
NEVER_RUN = SearchRunStats(runs=0, best=0, last_run_at=None)


#: The poller pauses a source/board after this many consecutive failed runs
#: (Task 7's PAUSE_AFTER); consecutive_failures only needs to look back this far.
PAUSE_AFTER = 3


async def consecutive_failures(
    session: AsyncSession,
    user_id: uuid.UUID,
    source: str,
    board: str | None,
    *,
    search_id: uuid.UUID | None = None,
    since: datetime | None = None,
) -> int:
    """Failed runs in a row, newest first, capped at PAUSE_AFTER.

    ``since`` restarts the streak: runs started at or before it (for example before the user
    re-saved the watchlist entry) are not counted, so a save grants a fresh three attempts.

    ``search_id`` narrows the streak to one saved search: a keyless aggregator driven by
    several searches shares ``(source, board=None)``, so without this a failing search's
    streak would be reset by another search's successes against the same aggregator (and
    vice versa). A board poll always passes ``search_id=None``, which keeps today's
    behaviour exactly (see the ``== None`` -> ``IS NULL`` note just below).
    """
    conditions = [
        PollRun.user_id == user_id,
        PollRun.source == source,
        # SQLAlchemy compiles `== None` to `IS NULL`, so this covers both
        # a real board and the no-board (board=None) case in one comparison.
        PollRun.board == board,
        PollRun.search_id == search_id,
    ]
    if since is not None:
        conditions.append(PollRun.started_at > since)
    rows = list(
        await session.scalars(
            select(PollRun)
            .where(*conditions)
            .order_by(PollRun.started_at.desc())
            .limit(PAUSE_AFTER)
        )
    )
    count = 0
    for run in rows:
        if run.error is None:
            break
        count += 1
    return count


async def upsert_scores(
    session: AsyncSession,
    user_id: uuid.UUID,
    job: Job,
    scores: list[tuple[str, int, dict[str, Any]]],
) -> None:
    existing = {
        s.track_id: s
        for s in await session.scalars(
            select(JobScore).where(JobScore.user_id == user_id, JobScore.job_id == job.id)
        )
    }
    now = datetime.now(UTC)
    for track_id, fit, rationale in scores:
        row = existing.get(track_id)
        if row is None:
            session.add(
                JobScore(
                    user_id=user_id,
                    job_id=job.id,
                    track_id=track_id,
                    fit_score=fit,
                    rationale_json=rationale,
                    scored_at=now,
                )
            )
        else:
            row.fit_score, row.rationale_json, row.scored_at = fit, rationale, now
    await session.flush()


async def scores_for_jobs(
    session: AsyncSession, user_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[JobScore]]:
    out: dict[uuid.UUID, list[JobScore]] = defaultdict(list)
    if not job_ids:
        return out
    for row in await session.scalars(
        select(JobScore)
        .where(JobScore.user_id == user_id, JobScore.job_id.in_(job_ids))
        .order_by(JobScore.fit_score.desc())
    ):
        out[row.job_id].append(row)
    return out
