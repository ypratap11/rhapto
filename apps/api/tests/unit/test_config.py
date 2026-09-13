from rhapto.config import Settings


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
