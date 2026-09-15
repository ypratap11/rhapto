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
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import (
    LlmFactory,
    current_user,
    get_llm_factory,
    get_session,
    get_settings_dep,
    get_state,
)
from rhapto.api.providers import provider_list
from rhapto.api.schemas import (
    LlmSettingsIn,
    LlmSettingsOut,
    LlmTestIn,
    LlmTestOut,
    SourceSettingIn,
    SourceSettingOut,
    SourceTestOut,
)
from rhapto.config import Settings
from rhapto.db.models import Aggregator
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.db.repositories.llm_settings import delete_llm_settings, upsert_llm_settings
from rhapto.engine.providers.llm import Message, SystemBlock
from rhapto.engine.providers.registry import PROVIDERS, ProviderInfo, model_for
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import aggregator_sources, get_aggregator
from rhapto.services.llm import env_llm_config, key_hint, redact, stored_llm_config
from rhapto.services.secrets import encrypt, fernet_for

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
FactoryDep = Annotated[LlmFactory, Depends(get_llm_factory)]


class Ping(BaseModel):
    """The smallest structured answer a provider can be asked for."""

    ok: bool


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
        model=model_for(info.id, body.model),
        api_key_encrypted=encrypt(settings, api_key),
    )
    await session.commit()
    return await _current(session, settings, user_id)


@router.delete("/settings/llm", status_code=204)
async def delete_llm_settings_endpoint(user_id: UserDep, session: SessionDep) -> Response:
    await delete_llm_settings(session, user_id)
    await session.commit()
    # 204 whether or not a row was there: the caller asked for "no stored provider", and that is
    # the state they get. The adapter cache is deliberately left alone: each entry carries the hash
    # of the key that built it, so a stale adapter can never be handed out for a different key.
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
    model = model_for(info.id, body.model)
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
        return LlmTestOut(ok=False, error=redact(str(exc), api_key)[:300])
    return LlmTestOut(ok=True, model=model)


#: A keyless source works out of the box, so it defaults to enabled; a keyed one needs the user
#: to add credentials first, so it defaults to disabled until they do.
KEYLESS_DEFAULT_ENABLED = True


async def _source_rows(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Aggregator]:
    return {row.source: row for row in await profile_repo.list_aggregators(session, user_id)}


@router.get("/settings/sources", response_model=list[SourceSettingOut])
async def list_source_settings(user_id: UserDep, session: SessionDep) -> list[SourceSettingOut]:
    rows = await _source_rows(session, user_id)
    stored = await creds_repo.credentialled_sources(session, user_id)
    out: list[SourceSettingOut] = []
    for info in aggregator_sources():
        row = rows.get(info.name)
        enabled = (
            row.enabled if row is not None else (KEYLESS_DEFAULT_ENABLED and not info.needs_key)
        )
        out.append(
            SourceSettingOut(
                id=info.name,
                label=info.label,
                needs_key=info.needs_key,
                fields=list(info.fields),
                enabled=enabled,
                key_set=info.name in stored,
            )
        )
    return out


@router.put("/settings/sources/{source}", response_model=SourceSettingOut)
async def put_source_setting(
    source: str, body: SourceSettingIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> SourceSettingOut:
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    fernet = fernet_for(settings)
    if body.credentials:
        await creds_repo.put_credentials(session, fernet, user_id, source, body.credentials)
    if body.enabled and info.needs_key:
        stored = await creds_repo.get_credentials(session, fernet, user_id, source)
        missing = [f for f in info.fields if not stored.get(f)]
        if missing:
            # Enabling a source we cannot call would show up later as a failed poll run with no
            # explanation; say which field is missing while the user is looking at the form.
            raise HTTPException(status_code=422, detail=f"{info.label} needs {', '.join(missing)}")
    rows = await _source_rows(session, user_id)
    row = rows.get(source)
    if row is None:
        row = Aggregator(user_id=user_id, source=source, enabled=body.enabled, keywords=[])
        session.add(row)
    else:
        row.enabled = body.enabled
    row.updated_at = datetime.now(UTC)
    await session.commit()
    stored_sources = await creds_repo.credentialled_sources(session, user_id)
    return SourceSettingOut(
        id=info.name,
        label=info.label,
        needs_key=info.needs_key,
        fields=list(info.fields),
        enabled=body.enabled,
        key_set=info.name in stored_sources,
    )


@router.post("/settings/sources/{source}/test", response_model=SourceTestOut)
async def test_source(
    source: str, user_id: UserDep, session: SessionDep, settings: SettingsDep, request: Request
) -> SourceTestOut:
    """One tiny search against the source. Never a 500: a failure is this endpoint's answer."""
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    credentials = await creds_repo.get_credentials(session, fernet_for(settings), user_id, source)
    http = get_state(request).discovery_http
    try:
        postings = await get_aggregator(source).fetch_search(
            http, SearchSpec(keywords=("program manager",)), credentials
        )
    except Exception as exc:
        return SourceTestOut(ok=False, error=redact(str(exc), *credentials.values())[:300])
    return SourceTestOut(ok=True, found=len(postings))
