"""Which LLM this user's work runs on: read it, set it, clear it, and probe it.

The stored key is write-only over HTTP. It goes in encrypted and comes back only as its last four
characters; every response here is built by `_current`, so there is one place that could ever leak
it.

Key precedence on a write is body → stored key (same provider) → environment. That lets a user
change their model without re-typing their key, and an `.env`-only deployment save a provider
choice without pasting one.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import LlmFactory, current_user, get_llm_factory, get_session, get_settings_dep
from rhapto.api.schemas import (
    LlmSettingsIn,
    LlmSettingsOut,
    LlmTestIn,
    LlmTestOut,
    ProviderInfoOut,
)
from rhapto.config import Settings
from rhapto.db.repositories.llm_settings import delete_llm_settings, upsert_llm_settings
from rhapto.engine.providers.llm import Message, SystemBlock
from rhapto.engine.providers.registry import PROVIDERS, ProviderInfo
from rhapto.services.llm import env_llm_config, stored_llm_config
from rhapto.services.secrets import encrypt

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
FactoryDep = Annotated[LlmFactory, Depends(get_llm_factory)]


class Ping(BaseModel):
    """The smallest structured answer a provider can be asked for."""

    ok: bool


def key_hint(api_key: str) -> str:
    """The last four characters, enough to recognise a key without revealing it."""
    return f"…{api_key[-4:]}"


def provider_list() -> list[ProviderInfoOut]:
    return [
        ProviderInfoOut(id=i.id, label=i.label, models=list(i.models), default=i.default)
        for i in PROVIDERS.values()
    ]


def known_provider(provider: str) -> ProviderInfo:
    info = PROVIDERS.get(provider)
    if info is None:
        raise HTTPException(status_code=422, detail=f"unknown provider {provider!r}")
    return info


def env_key_for(settings: Settings, info: ProviderInfo) -> str:
    """The environment's key for one provider (not necessarily the configured one)."""
    return str(getattr(settings, info.env_key.lower(), "") or "")


async def _current(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> LlmSettingsOut:
    """The stored row if there is one, else the environment's provider, else nothing configured."""
    config = await stored_llm_config(session, settings, user_id) or env_llm_config(settings)
    if config is None:
        return LlmSettingsOut(
            provider=None,
            model=None,
            key_set=False,
            key_hint=None,
            source="none",
            providers=provider_list(),
        )
    return LlmSettingsOut(
        provider=config.provider,
        model=config.model,
        key_set=True,
        key_hint=key_hint(config.api_key),
        source=config.source,
        providers=provider_list(),
    )


async def _key_for_write(
    session: AsyncSession,
    settings: Settings,
    user_id: uuid.UUID,
    info: ProviderInfo,
    body_key: str | None,
) -> str:
    submitted = (body_key or "").strip()
    if submitted:
        return submitted
    # Keeping the stored key means decrypting it, so a rotated server secret surfaces here as the
    # "re-enter your key" 409 rather than as a write that silently stores nothing usable.
    stored = await stored_llm_config(session, settings, user_id)
    if stored is not None and stored.provider == info.id:
        return stored.api_key
    from_env = env_key_for(settings, info)
    if from_env:
        return from_env
    raise HTTPException(status_code=422, detail=f"an API key is required for {info.label}")


@router.get("/settings/llm", response_model=LlmSettingsOut)
async def get_llm_settings_endpoint(
    user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> LlmSettingsOut:
    return await _current(session, settings, user_id)


@router.put("/settings/llm", response_model=LlmSettingsOut)
async def put_llm_settings(
    body: LlmSettingsIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> LlmSettingsOut:
    info = known_provider(body.provider)
    api_key = await _key_for_write(session, settings, user_id, info, body.api_key)
    await upsert_llm_settings(
        session,
        user_id,
        provider=info.id,
        model=body.model or info.default,
        api_key_encrypted=encrypt(settings, api_key),
    )
    await session.commit()
    return await _current(session, settings, user_id)


@router.delete("/settings/llm", status_code=204)
async def delete_llm_settings_endpoint(user_id: UserDep, session: SessionDep) -> Response:
    await delete_llm_settings(session, user_id)
    await session.commit()
    # 204 whether or not a row was there: the caller asked for "no stored provider", and that is
    # the state they get.
    return Response(status_code=204)


@router.post("/settings/llm/test", response_model=LlmTestOut)
async def test_llm_settings(
    body: LlmTestIn,
    user_id: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    llm_factory: FactoryDep,
) -> LlmTestOut:
    """Ask the provider for one tiny structured answer. Nothing is stored either way."""
    info = known_provider(body.provider)
    api_key = await _key_for_write(session, settings, user_id, info, body.api_key)
    model = body.model or info.default
    try:
        llm = llm_factory(info.id, model, api_key)
        await llm.complete_structured(
            system=[SystemBlock(text="Reply with ok=true.")],
            messages=[Message(role="user", content="ping")],
            output_schema=Ping,
            max_tokens=64,
        )
    except Exception as exc:
        # A failed probe is the endpoint's answer, not an error: a rejected key
        # (ProviderAuthError), an unreachable provider (EngineError) and anything an SDK raises
        # that the adapter does not map all come back as ok=false with the message, truncated so a
        # provider's wall of text cannot flood the UI.
        return LlmTestOut(ok=False, error=str(exc)[:300])
    return LlmTestOut(ok=True, model=model)
