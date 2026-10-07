from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, User
from rhapto.db.repositories.jobs import JobFilterParams, list_jobs
from rhapto.services.ranking import relevance_key


async def test_python_relevance_key_orders_exactly_like_the_sql(
    session: AsyncSession, user: User
) -> None:
    """The preview orders in-memory scores with `relevance_key`; production orders with SQL.
    Either drifting makes the preview measure a list nobody sees, so this fails if they differ."""
    # One clock. Postgres `now()` is the transaction start time, so the first statement of this
    # transaction fixes it for the query below as well, and ages are exact whole days.
    db_now = await session.scalar(select(func.now()))
    assert db_now is not None

    #            id  fit   age (days)  has posted_at
    spec = [
        (1, 90, 0, True),
        (2, 80, 10, True),  # decays to 78.0
        (3, 78, 0, True),  # 78.0: ties with 2, the newer wins
        (4, 85, 200, True),  # past the 90-day cap: 85 - 18 = 67.0
        (5, 67, 0, True),  # 67.0: ties with 4, the newer wins
        (6, 67, 0, True),  # identical to 5 in every column but id
        (7, None, 1, True),  # NULL fit sorts last
        (8, None, 5, True),
        (9, None, 5, True),  # NULL fit, same timestamp as 8: id decides
        (10, 70, 3, False),  # no posted_at: coalesces to discovered_at
        (11, 100, 400, True),  # ancient but strong: capped decay, 100 - 18 = 82.0
    ]
    jobs: list[Job] = []
    for n, fit, age, has_posted in spec:
        moment = db_now - timedelta(days=age)
        job = Job(
            id=uuid.UUID(int=n),
            user_id=user.id,
            source="manual",
            jd_text="x" * 60,
            dedupe_hash=f"h{n}",
            discovered_at=moment,
            posted_at=moment if has_posted else None,
            best_fit=fit,
        )
        session.add(job)
        jobs.append(job)
    await session.flush()

    sql_order = [
        job.id.int
        for job, _ in await list_jobs(
            session, JobFilterParams(user_id=user.id, sort="relevance", posted_within="any")
        )
    ]
    python_order = [j.id.int for j in sorted(jobs, key=lambda j: relevance_key(j, db_now))]
    assert python_order == sql_order
    # ... and both equal the order worked out by hand (decayed: 90, 82, 78 x2, 69.4, 67 x3; then the NULL fits).
    assert sql_order == [1, 11, 3, 2, 10, 5, 6, 4, 7, 8, 9]
