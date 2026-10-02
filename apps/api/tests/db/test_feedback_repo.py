from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import FeedbackRow, Job, Package, User
from rhapto.db.repositories import feedback as repo
from rhapto.db.repositories.users import get_or_create_user


async def _quick(session: AsyncSession, user: User, **kw: Any) -> FeedbackRow:
    row = await repo.insert(
        session,
        user_id=user.id,
        form="quick",
        page_area=kw.pop("page_area", "dashboard"),
        schema_version=1,
        answers={"kind": "bug", "text": "tester-a says hello"},
        app_version="0.1.0",
        job_id=kw.pop("job_id", None),
        package_id=kw.pop("package_id", None),
    )
    await session.commit()
    return row


async def _job_with_package(session: AsyncSession, user: User) -> tuple[Job, Package]:
    job = Job(
        user_id=user.id,
        source="manual",
        jd_text="Fictional role at Example Co.",
        dedupe_hash=uuid.uuid4().hex,
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
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
    )
    session.add(package)
    await session.commit()
    return job, package


async def test_insert_returns_the_row_with_server_defaults(
    session: AsyncSession, user: User
) -> None:
    row = await _quick(session, user)
    assert row.id is not None
    assert row.created_at is not None
    assert row.answers == {"kind": "bug", "text": "tester-a says hello"}


async def test_count_since_window_boundary(session: AsyncSession, user: User) -> None:
    now = datetime.now(UTC)
    old = await _quick(session, user)
    recent = await _quick(session, user)
    await session.execute(
        text("UPDATE feedback SET created_at = :t WHERE id = :id"),
        {"t": now - timedelta(hours=25), "id": old.id},
    )
    await session.execute(
        text("UPDATE feedback SET created_at = :t WHERE id = :id"),
        {"t": now - timedelta(hours=23), "id": recent.id},
    )
    await session.commit()
    assert await repo.count_since(session, user.id, now - timedelta(hours=24)) == 1
    assert await repo.count_since(session, user.id, now - timedelta(hours=26)) == 2
    assert await repo.count_since(session, user.id, now) == 0


async def test_count_since_is_per_user(session: AsyncSession, user: User) -> None:
    other = await get_or_create_user(session, "tester-b@example.com")
    await session.commit()
    await _quick(session, other)
    assert await repo.count_since(session, user.id, datetime.now(UTC) - timedelta(days=1)) == 0


async def test_owned_context_keeps_own_ids(session: AsyncSession, user: User) -> None:
    job, package = await _job_with_package(session, user)
    assert await repo.owned_context(session, user.id, job.id, package.id) == (job.id, package.id)
    assert await repo.owned_context(session, user.id, job.id, None) == (job.id, None)
    assert await repo.owned_context(session, user.id, None, None) == (None, None)


async def test_owned_context_nulls_another_users_ids_and_missing_ids(
    session: AsyncSession, user: User
) -> None:
    other = await get_or_create_user(session, "tester-b@example.com")
    await session.commit()
    job, package = await _job_with_package(session, other)
    assert await repo.owned_context(session, user.id, job.id, package.id) == (None, None)
    assert await repo.owned_context(session, user.id, uuid.uuid4(), uuid.uuid4()) == (None, None)


async def test_all_with_email_returns_every_users_rows_with_their_email(
    session: AsyncSession, user: User
) -> None:
    other = await get_or_create_user(session, "tester-b@example.com")
    await session.commit()
    await _quick(session, user)
    await _quick(session, other)
    pairs = await repo.all_with_email(session, None)
    assert sorted(email for _, email in pairs) == ["test@example.com", "tester-b@example.com"]
    future = datetime.now(UTC) + timedelta(days=1)
    assert await repo.all_with_email(session, future) == []


async def test_deleting_the_user_cascades_feedback_away(session: AsyncSession, user: User) -> None:
    await _quick(session, user)
    assert await session.scalar(select(func.count()).select_from(FeedbackRow)) == 1
    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(FeedbackRow)) == 0
