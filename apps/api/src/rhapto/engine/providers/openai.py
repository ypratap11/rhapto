from __future__ import annotations

from typing import Any

from rhapto.engine.providers.errors import ProviderAuthError, mentions_quota
from rhapto.engine.providers.llm import (
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    T,
    TokenUsage,
)

PROVIDER_ID = "openai"


def _auth_error(exc: BaseException) -> ProviderAuthError | None:
    """Map the SDK's credential failures; the SDK is imported here so the module stays import-light."""
    import openai

    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthError(PROVIDER_ID, str(exc))
    if isinstance(exc, openai.RateLimitError) and mentions_quota(str(exc)):
        return ProviderAuthError(PROVIDER_ID, str(exc))
    return None


class OpenAIProvider:
    """Structured output via the SDK's Pydantic-native parse helper (strict JSON schema under it).

    There is no prompt-caching flag to set: OpenAI caches long prompt prefixes automatically, so
    ``SystemBlock.cache`` is advisory here and the blocks are simply joined into one system message.
    """

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            import openai  # imported lazily so tests never need the SDK configured

            client = openai.AsyncOpenAI(api_key=api_key or None)
        self._client: Any = client

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        payload: list[dict[str, str]] = []
        if system:
            payload.append({"role": "system", "content": "\n\n".join(b.text for b in system)})
        payload.extend({"role": m.role, "content": m.content} for m in messages)
        try:
            response = await self._client.chat.completions.parse(
                model=self.model,
                messages=payload,
                response_format=output_schema,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            auth = _auth_error(exc)
            if auth is not None:
                raise auth from exc
            raise
        if not response.choices:
            raise MalformedOutputError(f"OpenAI returned no choices for {output_schema.__name__}")
        message = response.choices[0].message
        if message.refusal:
            raise MalformedOutputError(
                f"OpenAI refused to produce {output_schema.__name__}: {message.refusal}"
            )
        parsed = message.parsed
        if not isinstance(parsed, output_schema):
            raise MalformedOutputError(
                f"OpenAI returned no parsed {output_schema.__name__} (got {type(parsed).__name__})"
            )
        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None)
        return StructuredResult(
            value=parsed,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                cache_read_input_tokens=getattr(details, "cached_tokens", 0) or 0,
            ),
        )
