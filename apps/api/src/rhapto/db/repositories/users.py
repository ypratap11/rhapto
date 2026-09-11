from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        session.add(user)
        await session.flush()
    return user


async def list_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return list(await session.scalars(select(User.id).order_by(User.created_at)))
