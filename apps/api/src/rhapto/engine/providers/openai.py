from __future__ import annotations

from typing import Any

from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import (
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    T,
    TokenUsage,
)
from rhapto.engine.types import EngineError

PROVIDER_ID = "openai"


def _error_code(exc: Exception) -> str | None:
    """The API's machine-readable error code (e.g. `insufficient_quota`), if the SDK captured one."""
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            return str(error["code"])
    return None


def _mapped_error(exc: Exception) -> EngineError:
    """Every SDK failure leaves the adapter as an EngineError; the SDK is imported here so the
    module stays import-light.

    - truncation and content filters are retryable output problems (MalformedOutputError);
    - 401/403 and a spent quota are credential problems the user must fix (ProviderAuthError);
    - a plain 429, a timeout, a 5xx or a bad request is just an EngineError: retryable, not the
      user's key.
    """
    import openai

    if isinstance(exc, openai.LengthFinishReasonError):
        return MalformedOutputError(f"OpenAI hit the token cap before finishing the object: {exc}")
    if isinstance(exc, openai.ContentFilterFinishReasonError):
        return MalformedOutputError(f"OpenAI stopped on its content filter: {exc}")
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthError(PROVIDER_ID, str(exc))
    if isinstance(exc, openai.RateLimitError) and _error_code(exc) == "insufficient_quota":
        return ProviderAuthError(PROVIDER_ID, str(exc))
    return EngineError(str(exc))


class OpenAIProvider:
    """Structured output via the SDK's Pydantic-native parse helper (strict JSON schema under it).

    There is no prompt-caching flag to set: OpenAI caches long prompt prefixes automatically, so
    ``SystemBlock.cache`` is advisory here and the blocks are simply joined into one system message.
    The budget goes out as ``max_completion_tokens``: ``max_tokens`` is deprecated and rejected by
    the reasoning models this registry offers, and it covers reasoning tokens as well as the answer.
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
                max_completion_tokens=max_tokens,
            )
        except Exception as exc:
            raise _mapped_error(exc) from exc
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
