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
import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.db.repositories.llm_settings import get_llm_settings
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.registry import FAKE_PROVIDER_ID, build_llm, model_for, provider_info
from rhapto.services.secrets import SecretsError, decrypt

logger = logging.getLogger("rhapto.llm")

NOT_CONFIGURED_MESSAGE = "No LLM configured. Add a key in Settings."
# What the *user* is told when their stored key no longer decrypts. Lives here, not in the API, so
# the worker can report the same sentence on a task row without reaching into `rhapto.api`. The
# operator-facing text (which names RHAPTO_SECRET_KEY) stays on the exception.
KEY_UNREADABLE_MESSAGE = (
    "Your stored API key can no longer be decrypted (the server secret changed). "
    "Re-enter it in Settings."
)
# Below this, a "secret" is short enough to occur inside ordinary words, so redacting it would
# garble the message it is meant to protect. Real provider keys are decades longer.
MIN_REDACTABLE_SECRET = 8


class LLMNotConfiguredError(Exception):
    """No provider key is available for this user, from Settings or the environment."""

    def __init__(self, message: str = NOT_CONFIGURED_MESSAGE) -> None:
        super().__init__(message)


def key_hint(api_key: str) -> str:
    """ "…" plus the last four characters: enough for a user to recognise which key this is.

    A key of four characters or fewer gets no tail at all, because "the last four of five" is the
    key. Real provider keys are decades longer than that; this only guards test and placeholder
    values."""
    return f"…{api_key[-4:]}" if len(api_key) > 4 else "…"


def redact(message: str, *secrets: str) -> str:
    """`message` with every occurrence of each secret replaced by its hint.

    Provider SDKs quote the submitted key in their own error text ("Incorrect API key provided:
    …"), and that text is shown to the user, stored on task rows and published on the event bus.
    Run it through here first. Secrets shorter than `MIN_REDACTABLE_SECRET` are left alone: nothing
    stops a user saving a one-character key, and substituting it would turn every later provider
    error for them into unreadable confetti rather than protecting anything worth protecting."""
    for secret in secrets:
        if len(secret) >= MIN_REDACTABLE_SECRET:
            message = message.replace(secret, key_hint(secret))
    return message


@dataclass(frozen=True)
class LlmConfig:
    """Everything needed to build an adapter, plus where it came from (for the Settings UI)."""

    provider: str
    model: str
    api_key: str = field(repr=False)  # never in tracebacks or logs
    source: Literal["settings", "env"] = "env"


def env_llm_config(settings: Settings) -> LlmConfig | None:
    """The provider configured in the environment, or None when it has no key or is not supported."""
    info = provider_info(settings.rhapto_llm_provider)
    if info is None:
        return None
    # Settings field names are the env var names lowercased (ANTHROPIC_API_KEY → anthropic_api_key),
    # so the registry's env_key is enough to find the right field without a second mapping table.
    api_key = str(getattr(settings, info.env_key.lower(), "") or "")
    if not api_key:
        return None
    # RHAPTO_LLM_MODEL pairs with RHAPTO_LLM_PROVIDER. Someone who flips the provider and leaves
    # the model behind would otherwise send e.g. claude-sonnet-5 to OpenAI and have every run fail
    # at the provider, so a model belonging to another provider gives way to this one's default.
    return LlmConfig(
        provider=info.id,
        model=model_for(info.id, settings.rhapto_llm_model),
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
    # RHAPTO_LLM_PROVIDER=fake is an operator-level promise ("no vendor key, no network, no
    # bill") for the whole deployment. A user's stored key must not be able to override that
    # promise, so the env wins over Settings for exactly this one provider; every other provider
    # keeps the normal stored-over-env precedence.
    if settings.rhapto_llm_provider == FAKE_PROVIDER_ID:
        fake_config = env_llm_config(settings)
        if fake_config is not None:
            return fake_config
    config = await stored_llm_config(session, settings, user_id) or env_llm_config(settings)
    if config is None:
        raise LLMNotConfiguredError
    return config


async def provider_secrets(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID
) -> tuple[str, ...]:
    """Every key that could appear verbatim in a provider error for this user: the stored one and
    the environment's. For `redact`, on paths that report a provider's own message.

    Never raises: a key that cannot be decrypted cannot be in an error message either, and a
    caller in the middle of handling a failure must not be handed a second one."""
    keys: list[str] = []
    try:
        stored = await stored_llm_config(session, settings, user_id)
    except SecretsError:
        stored = None
    if stored is not None:
        keys.append(stored.api_key)
    from_env = env_llm_config(settings)
    if from_env is not None:
        keys.append(from_env.api_key)
    return tuple(keys)


# One adapter per (provider, model); the key hash decides whether the cached one is still
# current. A rotated key therefore replaces the old adapter instead of leaving it (and the old
# plaintext key inside it) alive for the life of the process, and the cache is bounded by the
# number of distinct provider/model pairs in use.
_CACHE: dict[tuple[str, str], tuple[str, LLMProvider]] = {}


def _key_hash(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def llm_for(config: LlmConfig) -> LLMProvider:
    slot = (config.provider, config.model)
    digest = _key_hash(config.api_key)
    cached = _CACHE.get(slot)
    if cached is not None and cached[0] == digest:
        return cached[1]
    provider = build_llm(config.provider, config.model, config.api_key)
    _CACHE[slot] = (digest, provider)
    return provider


def clear_llm_cache() -> None:
    """Drop every cached adapter. For tests, and for a process that just rotated a key."""
    _CACHE.clear()


async def resolve_llm(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> LLMProvider:
    return llm_for(await resolve_llm_config(session, settings, user_id))


FAKE_PROVIDER_WARNING = (
    "RHAPTO_LLM_PROVIDER=fake: every resume on this deployment is written by the deterministic "
    "fake provider, not by a language model. Bullets are copied verbatim from your blocks and no "
    "tailoring happens. This is for end-to-end tests and demos and must never be set in a "
    "deployment anyone relies on."
)


def warn_if_fake_llm(settings: Settings) -> bool:
    """Say loudly, once per process start, that this deployment writes nothing real."""
    if settings.rhapto_llm_provider != FAKE_PROVIDER_ID:
        return False
    logger.warning("%s", FAKE_PROVIDER_WARNING)
    return True
