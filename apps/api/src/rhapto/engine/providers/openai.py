from __future__ import annotations

from typing import Any

from pydantic import ValidationError

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
        return ProviderAuthError(PROVIDER_ID, str(exc), kind="quota")
    # OpenRouter signals exhausted credit with HTTP 402, which the SDK maps to a bare APIStatusError.
    if isinstance(exc, openai.APIStatusError) and exc.status_code == 402:
        return ProviderAuthError(PROVIDER_ID, str(exc), kind="quota")
    return EngineError(str(exc))


# Keywords stripped from the strict schema before it is sent. OpenAI's structured-output validator
# accepts a documented subset of JSON Schema, and a keyword outside it is rejected with a 400 —
# which would surface as an EngineError on a user's first real tailoring run. `default` is the one
# that matters (the engine's schemas are full of defaulted fields, and strict mode requires every
# property anyway, so a default can never apply); `title` goes too because it is pure noise in the
# prompt. Property *names* are never touched — JDExtract really does have a field called `title`.
_DROPPED_SCHEMA_KEYWORDS = frozenset({"default", "title"})
# Keys under these are user-chosen names mapping to sub-schemas, not schema keywords.
_NAME_KEYED_MAPS = frozenset({"properties", "$defs", "definitions", "patternProperties"})


def _pruned(node: Any) -> Any:
    """`node` with `_DROPPED_SCHEMA_KEYWORDS` removed from every schema object in it."""
    if isinstance(node, list):
        return [_pruned(item) for item in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _DROPPED_SCHEMA_KEYWORDS:
            continue
        if key in _NAME_KEYED_MAPS and isinstance(value, dict):
            out[key] = {name: _pruned(sub) for name, sub in value.items()}
        else:
            out[key] = _pruned(value)
    return out


def _strict_schema(output_schema: type[Any]) -> dict[str, Any]:
    """The strict JSON schema for a pydantic model: every property required, no extras anywhere.

    The SDK's own converter does that rewrite (it is what `.parse` uses internally), so this keeps
    one source of truth for it rather than reimplementing `$ref` inlining and `required` widening.
    """
    from openai.lib._pydantic import to_strict_json_schema

    schema = _pruned(to_strict_json_schema(output_schema))
    assert isinstance(schema, dict)
    return schema


class OpenAIProvider:
    """Structured output via an explicit strict `json_schema` response format.

    The request is built here rather than handed to the SDK's `.parse` helper so the schema that
    goes over the wire is the one this module decided on — `.parse` would send the converter's
    output verbatim, `default` keywords and all, and whether OpenAI's strict validator tolerates
    those is not something to find out on a user's first tailoring run. The answer is parsed back
    with `model_validate_json`, which is what `.parse` does once the schema is accepted.

    There is no prompt-caching flag to set: OpenAI caches long prompt prefixes automatically, so
    ``SystemBlock.cache`` is advisory here and the blocks are simply joined into one system message.
    The budget goes out as ``max_completion_tokens``: ``max_tokens`` is deprecated and rejected by
    the reasoning models this registry offers, and it covers reasoning tokens as well as the answer.
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        client: Any | None = None,
        base_url: str | None = None,
    ) -> None:
        """`base_url` points this adapter at an OpenAI-compatible host that is not OpenAI (Groq
        today; a local Ollama or vLLM server later). `None` keeps the SDK's own default, so the
        OpenAI path is byte-for-byte what it was before this parameter existed."""
        self.model = model
        if client is None:
            import openai  # imported lazily so tests never need the SDK configured

            client = openai.AsyncOpenAI(api_key=api_key or None, base_url=base_url or None)
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
        name = output_schema.__name__
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=payload,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": name,
                        "strict": True,
                        "schema": _strict_schema(output_schema),
                    },
                },
                max_completion_tokens=max_tokens,
            )
        except Exception as exc:
            raise _mapped_error(exc) from exc
        if not response.choices:
            raise MalformedOutputError(f"OpenAI returned no choices for {name}")
        choice = response.choices[0]
        message = choice.message
        if getattr(message, "refusal", None):
            raise MalformedOutputError(f"OpenAI refused to produce {name}: {message.refusal}")
        # `.create` reports these on the choice instead of raising the way `.parse` did, so they are
        # mapped here as well as in `_mapped_error`. Both are retryable output problems.
        finish = getattr(choice, "finish_reason", None)
        if finish == "length":
            raise MalformedOutputError(f"OpenAI hit the token cap before finishing {name}")
        if finish == "content_filter":
            raise MalformedOutputError(f"OpenAI stopped on its content filter before {name}")
        content = getattr(message, "content", None)
        if not content:
            raise MalformedOutputError(f"OpenAI returned no content for {name}")
        try:
            parsed = output_schema.model_validate_json(content)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"OpenAI returned content that is not a valid {name}: {exc}"
            ) from exc
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
