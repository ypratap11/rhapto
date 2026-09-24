import pytest

from rhapto.config import MissingSecretKeyError, Settings, get_settings


def test_defaults_when_env_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RHAPTO_LLM_MODEL", raising=False)
    settings = Settings(_env_file=None)
    # Empty means "the provider's default model"; services.llm fills it in from the registry.
    assert settings.rhapto_llm_model == ""
    assert settings.rhapto_llm_provider == "anthropic"
    assert settings.openai_api_key == "" and settings.gemini_api_key == ""
    assert settings.rhapto_secret_key == ""
    assert settings.rhapto_embedding_model == "BAAI/bge-small-en-v1.5"


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RHAPTO_LLM_MODEL", "claude-opus-5")
    assert Settings(_env_file=None).rhapto_llm_model == "claude-opus-5"


def test_provider_and_key_env_overrides(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RHAPTO_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-gemini")
    settings = Settings(_env_file=None)
    assert settings.rhapto_llm_provider == "openai"
    assert settings.openai_api_key == "sk-test-openai"
    assert settings.gemini_api_key == "sk-test-gemini"


def test_get_settings_requires_a_secret_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`Settings` alone still tolerates an empty `rhapto_secret_key` (the derive-from-API-token
    fallback in `services.secrets` needs that for its own tests), but `get_settings()` -- the
    singleton every real entrypoint uses -- must fail fast and name the variable, not run with a
    key implicitly derived from RHAPTO_API_TOKEN.

    `_no_provider_env` (autouse, tests/conftest.py) has already cleared RHAPTO_SECRET_KEY from
    the environment for this test.
    """
    get_settings.cache_clear()
    try:
        with pytest.raises(MissingSecretKeyError, match="RHAPTO_SECRET_KEY"):
            get_settings()
    finally:
        # `get_settings` is a process-wide singleton (`@lru_cache`) that the worker and API
        # entrypoints call for real, elsewhere in this same test session. Leaving the cache
        # cleared here would make the *next* test to call it -- with RHAPTO_SECRET_KEY deleted
        # by `_no_provider_env` for its own duration too -- hit this same error for real. Reseed
        # it with a working value (any non-empty string; get_settings only checks truthiness)
        # before handing back control.
        monkeypatch.setenv("RHAPTO_SECRET_KEY", "test-config-reseed-after-cache-clear")
        get_settings.cache_clear()
        get_settings()
