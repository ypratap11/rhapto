"""The user's LLM provider row. One per user; saving again replaces it."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.base import new_uuid
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
    """Insert or replace the user's row atomically (ON CONFLICT on the unique user_id)."""
    statement = (
        pg_insert(LlmSettingsRow)
        .values(
            id=new_uuid(),
            user_id=user_id,
            provider=provider,
            model=model,
            api_key_encrypted=api_key_encrypted,
        )
        .on_conflict_do_update(
            index_elements=[LlmSettingsRow.user_id],
            set_={
                "provider": provider,
                "model": model,
                "api_key_encrypted": api_key_encrypted,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(statement)
    session.expire_all()
    row = await get_llm_settings(session, user_id)
    assert row is not None  # the upsert just wrote it
    return row


async def delete_llm_settings(session: AsyncSession, user_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(delete(LlmSettingsRow).where(LlmSettingsRow.user_id == user_id)),
    )
    return bool(result.rowcount)
