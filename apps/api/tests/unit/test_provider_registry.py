import pytest

from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.gemini import GeminiProvider
from rhapto.engine.providers.openai import OpenAIProvider
from rhapto.engine.providers.registry import PROVIDERS, build_llm, provider_ids
from rhapto.engine.types import EngineError


def test_provider_ids_lists_the_three_supported_providers() -> None:
    assert provider_ids() == ["anthropic", "openai", "gemini"]


def test_registry_entries_carry_labels_env_keys_and_a_default_in_models() -> None:
    assert [PROVIDERS[p].label for p in provider_ids()] == ["Anthropic", "OpenAI", "Google Gemini"]
    assert [PROVIDERS[p].env_key for p in provider_ids()] == [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
    ]
    for provider_id, info in PROVIDERS.items():
        assert info.id == provider_id
        assert info.default in info.models, provider_id
        assert isinstance(info.models, tuple) and info.models


@pytest.mark.parametrize(
    ("provider_id", "model", "expected"),
    [
        ("anthropic", "claude-sonnet-5", AnthropicProvider),
        ("openai", "gpt-5", OpenAIProvider),
        ("gemini", "gemini-2.5-pro", GeminiProvider),
    ],
)
def test_build_llm_returns_the_adapter_for_each_provider(
    provider_id: str, model: str, expected: type
) -> None:
    provider = build_llm(provider_id, model, "sk-test-1234")
    assert isinstance(provider, expected)
    assert provider.model == model


def test_build_llm_passes_unlisted_model_ids_through_unchanged() -> None:
    provider = build_llm("openai", "gpt-5-pro-2026-01-01", "sk-test-1234")
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-5-pro-2026-01-01"


def test_build_llm_rejects_an_unknown_provider() -> None:
    with pytest.raises(EngineError, match="unknown provider 'nope'"):
        build_llm("nope", "gpt-5", "sk-test-1234")
