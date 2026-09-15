from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application, Package, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def _job(session: AsyncSession, user: User, external_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id=external_id,
        company="ExampleCo",
        title="Technical Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash=f"hash-{external_id}",
        repost_of=None,
        **kwargs,  # type: ignore[arg-type]
    )
    await session.flush()
    return job


async def test_flow_columns_start_empty(session: AsyncSession, user: User) -> None:
    job = await _job(session, user, "1", salary_text="$150,000 - $170,000")
    assert job.hidden_at is None
    assert job.unlisted_at is None
    assert job.miss_count == 0
    assert job.salary_text == "$150,000 - $170,000"
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    assert search.last_viewed_at is None


async def test_a_closed_reason_requires_the_closed_status(
    session: AsyncSession, user: User
) -> None:
    job = await _job(session, user, "2")
    good = Application(
        user_id=user.id,
        job_id=job.id,
        status="closed",
        closed_reason="rejected",
        notes="",
        status_history_json=[],
    )
    session.add(good)
    await session.flush()
    assert good.closed_reason == "rejected"
    bad = Application(
        user_id=user.id,
        job_id=job.id,
        status="screen",
        closed_reason="filled",
        notes="",
        status_history_json=[],
    )
    session.add(bad)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_follow_up_and_archived_are_plain_timestamps(
    session: AsyncSession, user: User
) -> None:
    job = await _job(session, user, "3")
    when = datetime.now(UTC)
    application = Application(
        user_id=user.id,
        job_id=job.id,
        status="applied",
        follow_up_at=when,
        notes="",
        status_history_json=[],
    )
    package = Package(
        user_id=user.id,
        job_id=job.id,
        track_id="t",
        version=1,
        status="draft",
        resume_json={},
        cover_note="",
        change_log="",
        guardrail_report_json={},
        jd_extract_json={},
        archived_at=when,
    )
    session.add_all([application, package])
    await session.flush()
    assert application.follow_up_at == when
    assert package.archived_at == when
