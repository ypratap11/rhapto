"""Tester feedback persistence. Insert-only, plus the one cross-user read (`all_with_email`), which
exists for the owner's CLI report and is imported by nothing under `rhapto.api`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import FeedbackRow, Job, Package, User


async def insert(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    form: str,
    page_area: str | None,
    schema_version: int,
    answers: dict[str, Any],
    app_version: str,
    job_id: uuid.UUID | None,
    package_id: uuid.UUID | None,
) -> FeedbackRow:
    """Add and flush one row (the caller commits); server defaults (id, created_at) are loaded."""
    row = FeedbackRow(
        user_id=user_id,
        form=form,
        page_area=page_area,
        schema_version=schema_version,
        answers=answers,
        app_version=app_version,
        job_id=job_id,
        package_id=package_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def count_since(session: AsyncSession, user_id: uuid.UUID, since: datetime) -> int:
    """Rows this user submitted at or after `since` (uses ix_feedback_user_created)."""
    count = await session.scalar(
        select(func.count())
        .select_from(FeedbackRow)
        .where(FeedbackRow.user_id == user_id, FeedbackRow.created_at >= since)
    )
    return int(count or 0)


async def owned_context(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID | None,
    package_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """The given ids, each kept only if that row exists and belongs to `user_id`, else None.

    A context pointer must never fail a submission and must never record another user's id.
    """
    kept_job: uuid.UUID | None = None
    kept_package: uuid.UUID | None = None
    if job_id is not None:
        kept_job = await session.scalar(
            select(Job.id).where(Job.id == job_id, Job.user_id == user_id)
        )
    if package_id is not None:
        kept_package = await session.scalar(
            select(Package.id).where(Package.id == package_id, Package.user_id == user_id)
        )
    return kept_job, kept_package


async def all_with_email(
    session: AsyncSession, since: datetime | None
) -> list[tuple[FeedbackRow, str]]:
    """Every user's feedback with the author's email, oldest first. CLI-only by design."""
    stmt = select(FeedbackRow, User.email).join(User, User.id == FeedbackRow.user_id)
    if since is not None:
        stmt = stmt.where(FeedbackRow.created_at >= since)
    stmt = stmt.order_by(FeedbackRow.created_at, FeedbackRow.id)
    return [(row, email) for row, email in (await session.execute(stmt)).all()]
