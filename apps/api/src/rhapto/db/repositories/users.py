from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    """Get the user row for `email`, creating it if absent.

    Uses `INSERT ... ON CONFLICT (email) DO NOTHING` followed by a re-select rather than a plain
    select-then-insert: a brand-new browser tab in access mode fires several requests in parallel
    on first load, so two concurrent first-sign-in calls for the same new email routinely race.
    With a plain insert the loser hits `users.email`'s unique constraint and raises an unhandled
    `IntegrityError` -- a 500 on the invited person's very first request. With `ON CONFLICT DO
    NOTHING`, the loser's insert is a no-op and the re-select simply reads the winner's row.
    """
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    stmt = pg_insert(User).values(email=email).on_conflict_do_nothing(index_elements=["email"])
    await session.execute(stmt)
    await session.flush()
    # A distinct variable name for the re-select, not a second assignment to `user` -- reassigning
    # the same name here makes mypy's overload resolution for the (identical) `session.scalar()`
    # call widen to `Any` instead of `User | None`, silently defeating the `no-any-return` check
    # below (verified: reveal_type differs between the two forms under `mypy --strict`).
    created = await session.scalar(select(User).where(User.email == email))
    assert created is not None  # the row now exists, either from this INSERT or the racing one
    return created


async def list_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return list(await session.scalars(select(User.id).order_by(User.created_at)))
