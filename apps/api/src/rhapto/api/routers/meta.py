from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session, get_settings_dep
from rhapto.api.schemas import BootstrapOut, HealthOut, MeOut
from rhapto.config import Settings
from rhapto.db.models import User
from rhapto.db.repositories.jobs import backfill_public_jobs
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.llm import LLMNotConfiguredError, resolve_llm_config
from rhapto.services.secrets import SecretsError

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


async def is_llm_configured(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> bool:
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
        llm_configured=await is_llm_configured(session, settings, user_id),
        auth_mode=settings.rhapto_auth_mode,
    )


@router.post("/me/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    user_id: Annotated[uuid.UUID, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BootstrapOut:
    """Idempotent, cheap on every call after the first: the web app calls this once per session,
    and it only ever does real work the one time `users.seeded_at` is still NULL. Kept entirely
    out of `current_user` (plan-review C6) so no other endpoint's request pays for it and no
    failure here can present as an auth failure.

    The claim is a single atomic `UPDATE ... WHERE seeded_at IS NULL RETURNING id`, not a read-
    then-write: Postgres's row-level locking means at most one of two concurrent callers ever gets
    a row back, so the backfill runs exactly once per account even under a real race -- no
    advisory lock, no new engine-access plumbing needed.
    """
    claim = await session.execute(
        text(
            "UPDATE users SET seeded_at = now() WHERE id = :uid AND seeded_at IS NULL RETURNING id"
        ),
        {"uid": str(user_id)},
    )
    if claim.first() is None:
        await session.rollback()
        return BootstrapOut(seeded=False)
    await backfill_public_jobs(session, user_id, public_sources=list(SOURCES.keys()))
    await session.commit()
    return BootstrapOut(seeded=True)
