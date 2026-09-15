from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SearchRow

#: Editing any of these makes the search the user's own, not the track's.
CRITERIA_FIELDS = ("keywords", "location", "remote")


async def list_searches(session: AsyncSession, user_id: uuid.UUID) -> list[SearchRow]:
    return list(
        await session.scalars(
            select(SearchRow).where(SearchRow.user_id == user_id).order_by(SearchRow.created_at)
        )
    )


async def get_search(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID
) -> SearchRow | None:
    result: SearchRow | None = await session.scalar(
        select(SearchRow).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
    )
    return result


async def create_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    keywords: list[str],
    location: str | None,
    remote: str,
    active: bool = True,
    derived_from_track_id: str | None = None,
) -> SearchRow:
    row = SearchRow(
        user_id=user_id,
        name=name,
        keywords=list(keywords),
        location=location,
        remote=remote,
        active=active,
        derived_from_track_id=derived_from_track_id,
    )
    session.add(row)
    await session.flush()
    return row


async def update_search(session: AsyncSession, row: SearchRow, **fields: Any) -> SearchRow:
    """Apply the given fields. Touching the criteria unlinks the search from its track."""
    for key, value in fields.items():
        if value is None and key in ("name", "remote", "active"):
            continue
        setattr(row, key, list(value) if key == "keywords" else value)
        if key in CRITERIA_FIELDS:
            row.derived_from_track_id = None
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def delete_search(session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(SearchRow).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
        ),
    )
    return bool(result.rowcount)
