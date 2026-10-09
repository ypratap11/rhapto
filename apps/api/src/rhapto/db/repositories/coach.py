"""Coach step events. Insert-only; the owner's funnel script reads the table on the server."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import CoachEvent


async def record_event(session: AsyncSession, user_id: uuid.UUID, step: str) -> None:
    """Record that `user_id` reached `step` today (UTC). A repeat on the same day is a no-op.

    `ON CONFLICT DO NOTHING` on the unique constraint, not check-then-insert: the client fires and
    forgets, so the same event can arrive twice at once. The caller commits.
    """
    await session.execute(
        pg_insert(CoachEvent)
        .values(user_id=user_id, step=step)
        .on_conflict_do_nothing(constraint="uq_coach_events_user_step_day")
    )
