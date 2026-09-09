from rhapto.config import Settings


def test_defaults_when_env_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("RHAPTO_LLM_MODEL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.rhapto_llm_model == "claude-sonnet-5"
    assert settings.rhapto_embedding_model == "BAAI/bge-small-en-v1.5"


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("RHAPTO_LLM_MODEL", "claude-opus-5")
    assert Settings(_env_file=None).rhapto_llm_model == "claude-opus-5"
