from __future__ import annotations

from dataclasses import dataclass

from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.gemini import GeminiProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.openai import OpenAIProvider
from rhapto.engine.types import EngineError


@dataclass(frozen=True)
class ProviderInfo:
    """One supported provider: what to call it, which models to offer, where its key lives."""

    id: str
    label: str
    models: tuple[str, ...]
    default: str
    env_key: str


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        id="anthropic",
        label="Anthropic",
        models=("claude-opus-5", "claude-sonnet-5"),
        default="claude-sonnet-5",
        env_key="ANTHROPIC_API_KEY",
    ),
    "openai": ProviderInfo(
        id="openai",
        label="OpenAI",
        models=("gpt-5", "gpt-5-mini"),
        default="gpt-5",
        env_key="OPENAI_API_KEY",
    ),
    "gemini": ProviderInfo(
        id="gemini",
        label="Google Gemini",
        models=("gemini-2.5-pro", "gemini-2.5-flash"),
        default="gemini-2.5-pro",
        env_key="GEMINI_API_KEY",
    ),
}


def provider_ids() -> list[str]:
    return list(PROVIDERS)


def build_llm(provider: str, model: str, api_key: str) -> LLMProvider:
    """Build the adapter for a provider id. `model` is passed through: the curated lists in
    PROVIDERS are suggestions for the UI, not a whitelist, so a newer model id still works."""
    if provider not in PROVIDERS:
        raise EngineError(f"unknown provider {provider!r}")
    if provider == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    if provider == "openai":
        return OpenAIProvider(model=model, api_key=api_key)
    return GeminiProvider(model=model, api_key=api_key)
