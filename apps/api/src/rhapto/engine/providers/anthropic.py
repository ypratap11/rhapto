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

TOOL_NAME = "emit"

PROVIDER_ID = "anthropic"

# Strict tool mode (``"strict": True``) was tried and rejected: with the forced-tool prompts here the
# model split its output across two tool_use blocks and returned empty sections. Malformed inputs are
# instead surfaced as MalformedOutputError so the pipeline can retry within its call budget.


def parse_tool_input(output_schema: type[T], payload: Any) -> T:
    """Validate a forced tool call's input, tolerating one wrapper object around the real payload.

    Observed failure modes: a placeholder input (``{"$PARAMETER_NAME": "$PARAMETER_VALUE"}``) and the
    whole object nested under a single key (the schema title, or one of its own fields). The wrapper
    case is unwrapped when the inner object validates; anything else raises MalformedOutputError.
    """
    try:
        return output_schema.model_validate(payload)
    except ValidationError as exc:
        if isinstance(payload, dict) and len(payload) == 1:
            (inner,) = payload.values()
            if isinstance(inner, dict):
                try:
                    return output_schema.model_validate(inner)
                except ValidationError:
                    pass
        keys = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise MalformedOutputError(
            f"{output_schema.__name__} tool input did not match the schema (keys: {keys}): "
            f"{exc.error_count()} validation error(s)"
        ) from exc


def _mapped_error(exc: Exception) -> EngineError:
    """Every SDK failure leaves the adapter as an EngineError; the SDK is imported here so the
    module stays import-light.

    401/403 is a credential problem and exhausted credit (a 400 "credit balance is too low", a 402
    or a billing_error) is a spent allowance; the user must fix either (ProviderAuthError, kind
    "auth" or "quota"). A 429, a timeout or a 5xx is a plain EngineError, retryable and not about
    the key.
    """
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return ProviderAuthError(PROVIDER_ID, str(exc))
    # Exhausted credit arrives as a 400 ("Your credit balance is too low ...") or a 402, not a 401.
    if isinstance(exc, anthropic.APIStatusError) and (
        exc.status_code == 402
        or getattr(exc, "type", None) == "billing_error"
        or "credit balance" in str(exc).lower()
    ):
        return ProviderAuthError(PROVIDER_ID, str(exc), kind="quota")
    return EngineError(str(exc))


class AnthropicProvider:
    """Structured output via a single forced tool call; static system blocks are prompt-cached."""

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            import anthropic  # imported lazily so tests never need the SDK configured

            client = anthropic.AsyncAnthropic(api_key=api_key or None)
        self._client: Any = client

    @staticmethod
    def _system_payload(system: list[SystemBlock]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for block in system:
            item: dict[str, Any] = {"type": "text", "text": block.text}
            if block.cache:
                item["cache_control"] = {"type": "ephemeral"}
            payload.append(item)
        return payload

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        schema = output_schema.model_json_schema()
        top_level = ", ".join(schema.get("properties", {}))
        tool = {
            "name": TOOL_NAME,
            "description": (
                f"Return the {output_schema.__name__}. The tool input is that object itself, "
                f"with these top-level keys: {top_level}. Do not wrap it in another object."
            ),
            "input_schema": schema,
        }
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=self._system_payload(system),
                messages=[{"role": m.role, "content": m.content} for m in messages],
                tools=[tool],
                tool_choice={"type": "tool", "name": TOOL_NAME},
            )
        except Exception as exc:
            raise _mapped_error(exc) from exc
        tool_use = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"), None
        )
        if tool_use is None:
            raise MalformedOutputError("Anthropic response contained no tool_use block")
        usage = response.usage
        return StructuredResult(
            value=parse_tool_input(output_schema, tool_use.input),
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
        )
