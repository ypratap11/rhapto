"""Deciding which LLM a given user's work runs on.

Precedence is stored row → environment → error. The stored row wins because it is the thing the
user just typed into Settings; the environment stays as the zero-UI path that keeps `.env`-only and
CLI setups working. Nothing falls back to a *different* provider: if the configured one has no key,
that is a setup problem to report, not something to paper over with someone else's key.

Adapters are cached per process. Building one opens an SDK client, and the worker resolves on every
task, so without a cache a busy worker would churn through HTTP clients for the same key. The cache
is keyed by a hash of the key rather than the key itself so no plaintext key sits in a long-lived
dict key; rotating a key therefore produces a new entry instead of reusing the stale client.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.db.repositories.llm_settings import get_llm_settings
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.registry import PROVIDERS, build_llm
from rhapto.services.secrets import decrypt

NOT_CONFIGURED_MESSAGE = "No LLM configured. Add a key in Settings."


class LLMNotConfiguredError(Exception):
    """No provider key is available for this user, from Settings or the environment."""

    def __init__(self, message: str = NOT_CONFIGURED_MESSAGE) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class LlmConfig:
    """Everything needed to build an adapter, plus where it came from (for the Settings UI)."""

    provider: str
    model: str
    api_key: str
    source: Literal["settings", "env"]


def env_llm_config(settings: Settings) -> LlmConfig | None:
    """The provider configured in the environment, or None when it has no key or is not supported."""
    info = PROVIDERS.get(settings.rhapto_llm_provider)
    if info is None:
        return None
    # Settings field names are the env var names lowercased (ANTHROPIC_API_KEY → anthropic_api_key),
    # so the registry's env_key is enough to find the right field without a second mapping table.
    api_key = str(getattr(settings, info.env_key.lower(), "") or "")
    if not api_key:
        return None
    return LlmConfig(
        provider=info.id,
        model=settings.rhapto_llm_model or info.default,
        api_key=api_key,
        source="env",
    )


async def stored_llm_config(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> LlmConfig | None:
    """The user's saved provider with its key decrypted, or None when they have not saved one."""
    row = await get_llm_settings(session, user_id)
    if row is None:
        return None
    return LlmConfig(
        provider=row.provider,
        model=row.model,
        api_key=decrypt(settings, row.api_key_encrypted),
        source="settings",
    )


async def resolve_llm_config(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> LlmConfig:
    config = await stored_llm_config(session, settings, user_id) or env_llm_config(settings)
    if config is None:
        raise LLMNotConfiguredError
    return config


_CACHE: dict[tuple[str, str, str], LLMProvider] = {}


def llm_for(config: LlmConfig) -> LLMProvider:
    key = (config.provider, config.model, hashlib.sha256(config.api_key.encode()).hexdigest())
    provider = _CACHE.get(key)
    if provider is None:
        provider = build_llm(config.provider, config.model, config.api_key)
        _CACHE[key] = provider
    return provider


def clear_llm_cache() -> None:
    """Drop every cached adapter. For tests, and for a process that just rotated a key."""
    _CACHE.clear()


async def resolve_llm(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> LLMProvider:
    return llm_for(await resolve_llm_config(session, settings, user_id))
