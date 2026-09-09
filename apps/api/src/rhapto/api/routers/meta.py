from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import HealthOut, MeOut
from rhapto.db.models import User

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/me", response_model=MeOut)
async def me(
    user_id: Annotated[uuid.UUID, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MeOut:
    user = await session.get(User, user_id)
    assert user is not None
    return MeOut(email=user.email, user_id=user.id)
