"""The user's uploaded resume document row. One per user; re-uploading replaces it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import ResumeDocumentRow


async def get_document(session: AsyncSession, user_id: uuid.UUID) -> ResumeDocumentRow | None:
    row: ResumeDocumentRow | None = await session.scalar(
        select(ResumeDocumentRow).where(ResumeDocumentRow.user_id == user_id)
    )
    return row


async def upsert_document(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    filename: str,
    path: str,
    parsed: dict[str, Any],
) -> ResumeDocumentRow:
    row = await get_document(session, user_id)
    if row is None:
        row = ResumeDocumentRow(user_id=user_id)
        session.add(row)
    row.filename = filename
    row.path = path
    row.parsed_json = parsed
    row.uploaded_at = datetime.now(UTC)
    await session.flush()
    return row


async def delete_document(session: AsyncSession, user_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(ResumeDocumentRow).where(ResumeDocumentRow.user_id == user_id)
        ),
    )
    return bool(result.rowcount)
