"""Per-user LLM resolution: stored row, then environment, then a clear error."""

from __future__ import annotations

import base64
import dataclasses
import uuid
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.openai import OpenAIProvider
from rhapto.services import llm as llm_service
from rhapto.services.llm import (
    LlmConfig,
    LLMNotConfiguredError,
    clear_llm_cache,
    env_llm_config,
    llm_for,
    resolve_llm,
    resolve_llm_config,
)

SECRET = base64.urlsafe_b64encode(b"s" * 32).decode()
USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_llm_cache()


def _settings(**kwargs: str) -> Settings:
    return Settings(_env_file=None, rhapto_secret_key=SECRET, **kwargs)  # type: ignore[arg-type]


def _session() -> AsyncSession:
    """`stored_llm_config` is always monkeypatched in these tests, so the session is never used."""
    return cast("AsyncSession", object())


def test_env_llm_config_uses_the_provider_default_model_when_unset() -> None:
    config = env_llm_config(
        _settings(rhapto_llm_provider="anthropic", anthropic_api_key="sk-test-a")
    )
    assert config == LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key="sk-test-a", source="env"
    )


def test_env_llm_config_honours_an_explicit_model() -> None:
    config = env_llm_config(
        _settings(
            rhapto_llm_provider="openai", openai_api_key="sk-test-o", rhapto_llm_model="gpt-5-mini"
        )
    )
    assert config is not None and config.model == "gpt-5-mini" and config.provider == "openai"


def test_env_llm_config_reads_the_key_field_matching_the_provider() -> None:
    settings = _settings(
        rhapto_llm_provider="gemini", anthropic_api_key="sk-test-a", gemini_api_key="sk-test-g"
    )
    config = env_llm_config(settings)
    assert config is not None and config.api_key == "sk-test-g"
    assert config.model == "gemini-2.5-pro"


def test_env_llm_config_is_none_without_a_key() -> None:
    assert env_llm_config(_settings(rhapto_llm_provider="anthropic")) is None


def test_env_llm_config_is_none_for_an_unknown_provider() -> None:
    assert (
        env_llm_config(_settings(rhapto_llm_provider="acme", anthropic_api_key="sk-test-a")) is None
    )


async def test_stored_config_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = LlmConfig(
        provider="openai", model="gpt-5", api_key="sk-test-stored", source="settings"
    )

    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig:
        return stored

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    settings = _settings(rhapto_llm_provider="anthropic", anthropic_api_key="sk-test-env")
    assert await resolve_llm_config(_session(), settings, USER_ID) == stored


async def test_falls_back_to_the_environment_when_no_row_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig | None:
        return None

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    settings = _settings(rhapto_llm_provider="anthropic", anthropic_api_key="sk-test-env")
    config = await resolve_llm_config(_session(), settings, USER_ID)
    assert config.source == "env" and config.model == "claude-sonnet-5"


async def test_unknown_env_provider_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig | None:
        return None

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    settings = _settings(rhapto_llm_provider="acme", anthropic_api_key="sk-test-env")
    with pytest.raises(LLMNotConfiguredError, match="Add a key in Settings"):
        await resolve_llm_config(_session(), settings, USER_ID)


async def test_no_key_anywhere_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig | None:
        return None

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    with pytest.raises(LLMNotConfiguredError) as exc:
        await resolve_llm_config(_session(), _settings(), USER_ID)
    assert str(exc.value) == "No LLM configured. Add a key in Settings."


async def test_resolve_llm_builds_the_adapter_for_the_resolved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig:
        return LlmConfig(
            provider="openai", model="gpt-5-mini", api_key="sk-test-stored", source="settings"
        )

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    provider = await resolve_llm(_session(), _settings(), USER_ID)
    assert isinstance(provider, OpenAIProvider) and provider.model == "gpt-5-mini"


def test_llm_for_caches_per_provider_model_and_key() -> None:
    config = LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key="sk-test-1", source="env"
    )
    first = llm_for(config)
    assert isinstance(first, AnthropicProvider)
    assert llm_for(config) is first
    assert llm_for(dataclasses.replace(config, source="settings")) is first


def test_llm_for_rebuilds_when_the_key_changes() -> None:
    base = LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key="sk-test-1", source="env"
    )
    rotated = dataclasses.replace(base, api_key="sk-test-2")
    assert llm_for(base) is not llm_for(rotated)
    assert llm_for(dataclasses.replace(base, model="claude-opus-5")) is not llm_for(base)


def test_clear_llm_cache_drops_built_adapters() -> None:
    config = LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key="sk-test-1", source="env"
    )
    first = llm_for(config)
    clear_llm_cache()
    assert llm_for(config) is not first
