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
    key_hint,
    llm_for,
    provider_secrets,
    redact,
    resolve_llm,
    resolve_llm_config,
)
from rhapto.services.secrets import SecretsError

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


async def test_env_fake_wins_over_a_stored_real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 4. RHAPTO_LLM_PROVIDER=fake is `docker-compose.e2e.yml`'s promise of "no vendor
    key, no network, no bill" for the whole deployment. A user who saved a real key in Settings
    must not be able to defeat that promise -- the stack would silently call the paid vendor while
    the fake-provider banner (`warn_if_fake_llm`) still told everyone it was safe."""
    stored = LlmConfig(
        provider="anthropic", model="claude-sonnet-5", api_key="sk-real-stored", source="settings"
    )

    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig:
        return stored

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    settings = _settings(rhapto_llm_provider="fake")
    config = await resolve_llm_config(_session(), settings, USER_ID)
    assert config.provider == "fake" and config.source == "env"


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


def test_llm_config_repr_never_shows_the_key() -> None:
    from rhapto.services.llm import LlmConfig

    config = LlmConfig(
        provider="openai", model="gpt-5", api_key="sk-test-secret-9999", source="env"
    )
    assert "sk-test" not in repr(config) and "sk-test" not in str(config)


def test_rotating_the_key_replaces_the_cached_adapter() -> None:
    from rhapto.services.llm import LlmConfig, clear_llm_cache, llm_for

    clear_llm_cache()
    first = llm_for(LlmConfig(provider="openai", model="gpt-5", api_key="sk-test-a", source="env"))
    again = llm_for(LlmConfig(provider="openai", model="gpt-5", api_key="sk-test-a", source="env"))
    rotated = llm_for(
        LlmConfig(provider="openai", model="gpt-5", api_key="sk-test-b", source="env")
    )
    assert first is again and rotated is not first
    # The old adapter is no longer reachable from the cache: asking with the old key rebuilds.
    assert (
        llm_for(LlmConfig(provider="openai", model="gpt-5", api_key="sk-test-a", source="env"))
        is not first
    )


def test_key_hint_keeps_only_the_last_four_characters() -> None:
    assert key_hint("sk-test-abcd1234") == "…1234"
    # Four characters or fewer: "the last four" would be the whole key.
    assert key_hint("test") == "…" and key_hint("") == "…"


def test_redact_swaps_every_secret_for_its_hint() -> None:
    message = "Incorrect API key provided: sk-test-abcd1234. Check your key."
    assert redact(message, "sk-test-abcd1234") == (
        "Incorrect API key provided: …1234. Check your key."
    )
    assert redact(
        "two: sk-test-aaaa1111 sk-test-bbbb2222", "sk-test-aaaa1111", "sk-test-bbbb2222"
    ) == ("two: …1111 …2222")
    # An empty secret must not turn every gap in the message into a hint.
    assert redact("nothing to hide", "") == "nothing to hide"


async def test_provider_secrets_collects_the_stored_and_environment_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stored(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> LlmConfig:
        return LlmConfig(
            provider="openai", model="gpt-5", api_key="sk-test-stored", source="settings"
        )

    monkeypatch.setattr(llm_service, "stored_llm_config", fake_stored)
    settings = _settings(rhapto_llm_provider="anthropic", anthropic_api_key="sk-test-env")
    assert await provider_secrets(_session(), settings, USER_ID) == (
        "sk-test-stored",
        "sk-test-env",
    )


async def test_provider_secrets_survives_an_unreadable_stored_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Called while reporting a failure: a second exception there would lose the first one."""

    async def boom(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> LlmConfig:
        raise SecretsError("stored key cannot be decrypted")

    monkeypatch.setattr(llm_service, "stored_llm_config", boom)
    settings = _settings(rhapto_llm_provider="anthropic", anthropic_api_key="sk-test-env")
    assert await provider_secrets(_session(), settings, USER_ID) == ("sk-test-env",)


def test_env_llm_config_drops_a_model_that_belongs_to_another_provider() -> None:
    """Copying .env.example and flipping RHAPTO_LLM_PROVIDER must not send Anthropic's model id to
    OpenAI: every run would fail at the provider while /me still reported llm_configured."""
    config = env_llm_config(
        _settings(
            rhapto_llm_provider="openai",
            openai_api_key="sk-test-o",
            rhapto_llm_model="claude-sonnet-5",
        )
    )
    assert config is not None and config.model == "gpt-5"


def test_env_llm_config_still_honours_an_uncurated_model_id() -> None:
    """A model released after this build is not a mistake; only another provider's id is."""
    config = env_llm_config(
        _settings(
            rhapto_llm_provider="openai",
            openai_api_key="sk-test-o",
            rhapto_llm_model="gpt-5-pro-2026-01-01",
        )
    )
    assert config is not None and config.model == "gpt-5-pro-2026-01-01"


def test_redact_leaves_a_short_secret_alone() -> None:
    """A one-character "key" occurs inside ordinary words, so substituting it would garble every
    provider message the user is shown without protecting anything."""
    assert redact("Rate limit reached for gpt-5", "a") == "Rate limit reached for gpt-5"
    assert redact("quota for sk-short", "sk-short") == "quota for …hort"
