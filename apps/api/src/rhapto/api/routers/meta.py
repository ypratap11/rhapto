from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session, get_settings_dep
from rhapto.api.schemas import HealthOut, MeOut
from rhapto.config import Settings
from rhapto.db.models import User
from rhapto.services.llm import LLMNotConfiguredError, resolve_llm_config
from rhapto.services.secrets import SecretsError

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


async def llm_configured(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> bool:
    """Whether tailoring would have a provider to run on. An unreadable stored key counts as not
    configured: the user has to re-enter it either way."""
    try:
        await resolve_llm_config(session, settings, user_id)
    except (LLMNotConfiguredError, SecretsError):
        return False
    return True


@router.get("/me", response_model=MeOut)
async def me(
    user_id: Annotated[uuid.UUID, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> MeOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=503, detail="user not bootstrapped")
    return MeOut(
        email=user.email,
        user_id=user.id,
        llm_configured=await llm_configured(session, settings, user_id),
    )
