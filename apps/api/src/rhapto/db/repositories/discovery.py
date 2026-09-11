from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
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
    """Newest run per (source, board)."""
    rows = await session.scalars(
        select(PollRun)
        .where(PollRun.user_id == user_id)
        .order_by(PollRun.source, PollRun.board, PollRun.started_at.desc())
        .distinct(PollRun.source, PollRun.board)
    )
    return sorted(rows, key=lambda r: r.started_at, reverse=True)


#: The poller pauses a source/board after this many consecutive failed runs
#: (Task 7's PAUSE_AFTER); consecutive_failures only needs to look back this far.
PAUSE_AFTER = 3


async def consecutive_failures(
    session: AsyncSession, user_id: uuid.UUID, source: str, board: str | None
) -> int:
    rows = list(
        await session.scalars(
            select(PollRun)
            .where(
                PollRun.user_id == user_id,
                PollRun.source == source,
                # SQLAlchemy compiles `== None` to `IS NULL`, so this covers both
                # a real board and the no-board (board=None) case in one comparison.
                PollRun.board == board,
            )
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
        for s in await session.scalars(select(JobScore).where(JobScore.job_id == job.id))
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
