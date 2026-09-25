from __future__ import annotations

from dataclasses import dataclass

from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.fake import FAKE_MODEL, DeterministicFakeProvider
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
    #: For an OpenAI-compatible endpoint that is not OpenAI itself, the API root to talk to.
    #: `None` means the SDK's own default. This is the whole of what separates Groq (and, later, a
    #: local Ollama or vLLM server) from OpenAI: same wire protocol, same adapter, different host.
    base_url: str | None = None


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
    # Groq serves open-weight models behind OpenAI's own wire protocol, and its free tier is real:
    # it is the cheapest honest answer for someone who cannot put a card down, which is most of the
    # people this tool exists for. The model ids below are suggestions for the picker, not a
    # whitelist (see `model_for`), because Groq's catalogue turns over faster than this file does.
    #
    # Caveat worth knowing before trusting it: `OpenAIProvider` sends a STRICT `json_schema`
    # response format, and support for that is per-model on Groq rather than universal. A model
    # that only honours `json_object` will come back as MalformedOutputError, not as a silently
    # wrong resume — the guardrails still hold — but it will fail. Measure a model before relying
    # on it.
    "groq": ProviderInfo(
        id="groq",
        label="Groq (free tier)",
        models=("llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct"),
        default="llama-3.3-70b-versatile",
        env_key="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
    ),
    # OpenRouter fronts dozens of models from many vendors behind OpenAI's protocol, which makes
    # it the cheapest way to try an open model without hosting one: the local box cannot run
    # anything useful (an 8B at 4-bit needs ~5GB against 940MB free), and a GPU host costs more
    # per month than the API costs per year at this volume. Model ids here are namespaced by
    # vendor and are suggestions, not a whitelist -- see `model_for`.
    "openrouter": ProviderInfo(
        id="openrouter",
        label="OpenRouter",
        models=(
            "anthropic/claude-haiku-4.5",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
        ),
        default="meta-llama/llama-3.3-70b-instruct",
        env_key="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    ),
}

#: Providers spoken to with the OpenAI adapter. Membership, not the provider id, is what picks the
#: adapter in `build_llm`, so adding an OpenAI-compatible host is one PROVIDERS entry and one name
#: here — no new adapter, no new error mapping, no new tests of the wire format.
OPENAI_COMPATIBLE = frozenset({"openai", "groq", "openrouter"})


FAKE_PROVIDER_ID = "fake"

#: Providers that exist but are never offered in Settings and can never be saved by a user.
#: `env_key` is RHAPTO_LLM_PROVIDER itself: asking for the fake *is* the credential, which is why
#: the e2e stack needs no key at all. Kept out of PROVIDERS so `provider_list()` and the Settings
#: router's `known_provider()` stay exactly as strict as they were.
ENV_ONLY_PROVIDERS: dict[str, ProviderInfo] = {
    FAKE_PROVIDER_ID: ProviderInfo(
        id=FAKE_PROVIDER_ID,
        label="Deterministic fake (testing only)",
        models=(FAKE_MODEL,),
        default=FAKE_MODEL,
        env_key="RHAPTO_LLM_PROVIDER",
    )
}


def provider_info(provider: str) -> ProviderInfo | None:
    """Any provider this build can actually construct, selectable or not."""
    return PROVIDERS.get(provider) or ENV_ONLY_PROVIDERS.get(provider)


# {model id: the provider that curates it}. Precomputed once so `model_for` is a dict lookup
# rather than a scan of every provider's list on each write. Only `PROVIDERS` (the user-selectable
# providers), so `model_for("fake", "claude-sonnet-5")` sees the id owned by anthropic and falls
# back to the fake's own default rather than treating it as the fake's own model.
_MODEL_OWNER: dict[str, str] = {
    model: info.id for info in PROVIDERS.values() for model in info.models
}


def provider_ids() -> list[str]:
    return list(PROVIDERS)


def model_for(provider: str, model: str) -> str:
    """The model id to actually use for `provider`.

    Empty means "whatever this provider's default is". An unlisted id passes through — the curated
    lists are suggestions for the picker and the env, not a whitelist, so a model released after
    this build still works. But an id that belongs to a *different* provider's list is a leftover
    (a form that kept its previous selection, or RHAPTO_LLM_MODEL left over from another
    RHAPTO_LLM_PROVIDER), and sending it would make every run fail at the provider: it gives way to
    this provider's default. An unknown provider has no opinion to offer, so the id is returned
    unchanged; callers validate the provider first.
    """
    info = provider_info(provider)
    if info is None:
        return model
    if not model:
        return info.default
    owner = _MODEL_OWNER.get(model)
    return info.default if owner is not None and owner != provider else model


def build_llm(provider: str, model: str, api_key: str) -> LLMProvider:
    """Build the adapter for a provider id. `model` is passed through: the curated lists in
    PROVIDERS are suggestions for the UI, not a whitelist, so a newer model id still works."""
    if provider == FAKE_PROVIDER_ID:
        return DeterministicFakeProvider(model=model or FAKE_MODEL)
    if provider not in PROVIDERS:
        raise EngineError(f"unknown provider {provider!r}")
    if provider == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key)
    if provider in OPENAI_COMPATIBLE:
        return OpenAIProvider(model=model, api_key=api_key, base_url=PROVIDERS[provider].base_url)
    return GeminiProvider(model=model, api_key=api_key)
