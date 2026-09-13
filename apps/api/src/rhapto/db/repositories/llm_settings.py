"""The user's LLM provider row. One per user; saving again replaces it."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import LlmSettingsRow


async def get_llm_settings(session: AsyncSession, user_id: uuid.UUID) -> LlmSettingsRow | None:
    row: LlmSettingsRow | None = await session.scalar(
        select(LlmSettingsRow).where(LlmSettingsRow.user_id == user_id)
    )
    return row


async def upsert_llm_settings(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    provider: str,
    model: str,
    api_key_encrypted: str,
) -> LlmSettingsRow:
    row = await get_llm_settings(session, user_id)
    if row is None:
        row = LlmSettingsRow(user_id=user_id)
        session.add(row)
    row.provider = provider
    row.model = model
    row.api_key_encrypted = api_key_encrypted
    await session.flush()
    return row


async def delete_llm_settings(session: AsyncSession, user_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(delete(LlmSettingsRow).where(LlmSettingsRow.user_id == user_id)),
    )
    return bool(result.rowcount)
