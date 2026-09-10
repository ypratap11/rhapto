from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def create_application(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    package_id: uuid.UUID | None,
) -> Application:
    row = Application(
        user_id=user_id,
        job_id=job_id,
        package_id=package_id,
        status="queued",
        notes="",
        status_history_json=[{"status": "queued", "at": _now_iso()}],
    )
    session.add(row)
    await session.flush()
    return row


async def get_application(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> Application | None:
    result: Application | None = await session.scalar(
        select(Application).where(Application.user_id == user_id, Application.id == application_id)
    )
    return result


async def list_applications(session: AsyncSession, user_id: uuid.UUID) -> list[Application]:
    return list(
        await session.scalars(
            select(Application)
            .where(Application.user_id == user_id)
            .order_by(Application.created_at.desc())
        )
    )


def set_status(application: Application, status: str) -> None:
    if status == application.status:
        return
    application.status = status
    application.status_history_json = [
        *application.status_history_json,
        {"status": status, "at": _now_iso()},
    ]
    if status == "applied" and application.applied_at is None:
        application.applied_at = datetime.now(UTC)


async def delete_application(
    session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID
) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(Application).where(
                Application.user_id == user_id, Application.id == application_id
            )
        ),
    )
    return bool(result.rowcount)
