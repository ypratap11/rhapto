from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from rhapto.engine.providers.errors import ProviderAuthError, mentions_quota
from rhapto.engine.providers.llm import (
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    T,
    TokenUsage,
)
from rhapto.engine.types import EngineError

PROVIDER_ID = "gemini"

# A bad key on the Gemini Developer API is a 400 INVALID_ARGUMENT, not a 401: the status line alone
# cannot tell it apart from a malformed request, so the message has to be read.
_INVALID_KEY_MARKERS = ("api key not valid", "api_key_invalid", "invalid api key")


def _mapped_error(exc: Exception) -> EngineError:
    """Every SDK failure leaves the adapter as an EngineError; the SDK is imported here so the
    module stays import-light.

    401/403, a 400 that names the API key, and a 429 whose message mentions quota are credential
    problems the user must fix (Gemini has no machine-readable code for the last one). A 5xx, a
    timeout or any other bad request is a plain EngineError: retryable, not the user's key.
    """
    from google.genai import errors as genai_errors

    if not isinstance(exc, genai_errors.APIError):
        return EngineError(str(exc))
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or str(exc)
    lowered = message.lower()
    if code in (401, 403) or any(marker in lowered for marker in _INVALID_KEY_MARKERS):
        return ProviderAuthError(PROVIDER_ID, message)
    # Only explicit signals are quota; a bare per-minute RESOURCE_EXHAUSTED stays a retryable EngineError.
    if code == 429 and (mentions_quota(message) or "billing" in lowered or "credit" in lowered):
        return ProviderAuthError(PROVIDER_ID, message, kind="quota")
    return EngineError(message)


# Content-policy stops. Each leaves partial or no JSON behind, so without this the run would fail as
# "did not return valid JSON" and hide the reason.
_SAFETY_STOPS = frozenset({"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"})


def _finish_reason(response: Any) -> str:
    """The first candidate's finish reason as a plain name ("STOP", "MAX_TOKENS", ...), or ""."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    reason = getattr(candidates[0], "finish_reason", None)
    if reason is None:
        return ""
    return str(getattr(reason, "name", reason))


class GeminiProvider:
    """Structured output via `response_mime_type=application/json` plus a `response_json_schema`.

    The schema goes over as the model's own JSON Schema (`model_json_schema()`, a dict the SDK
    forwards untouched), NOT as `response_schema`. That older field takes Gemini's OpenAPI subset,
    and the SDK's conversion into it carries `additionalProperties` through as
    `additional_properties`, which the API rejects -- so every schema with `extra="forbid"`
    (JDExtract, ComposeOutput) failed with a 400 on every live call until 2026-09-29, while the unit
    tests, which never built the wire request, stayed green.

    Gemini has no per-block cache control (implicit caching applies to long prefixes), so the system
    blocks are joined into one `system_instruction` and `SystemBlock.cache` is advisory.
    """

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            from google import genai  # imported lazily so tests never need the SDK configured

            client = genai.Client(api_key=api_key or None)
        self._client: Any = client

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        contents = [
            {
                "role": "user" if m.role == "user" else "model",
                "parts": [{"text": m.content}],
            }
            for m in messages
        ]
        config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "response_json_schema": output_schema.model_json_schema(),
            "max_output_tokens": max_tokens,
        }
        if system:
            # Omitted when empty: an empty string becomes an empty system turn on the wire.
            config["system_instruction"] = "\n\n".join(b.text for b in system)
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as exc:
            raise _mapped_error(exc) from exc
        name = output_schema.__name__
        finish = _finish_reason(response)
        if finish == "MAX_TOKENS":
            # Thinking tokens count against max_output_tokens, so a long answer can run out early.
            raise MalformedOutputError(f"Gemini hit the token cap before finishing {name}")
        if finish in _SAFETY_STOPS:
            raise MalformedOutputError(f"Gemini stopped on its safety filter before {name}")
        if finish == "RECITATION":
            raise MalformedOutputError(f"Gemini stopped on its recitation check before {name}")
        text = response.text
        if not text:
            raise MalformedOutputError(
                f"Gemini returned no text for {name} (the response was empty or blocked)"
            )
        try:
            value = output_schema.model_validate_json(text)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"{name} did not match the schema: {exc.error_count()} validation error(s)"
            ) from exc
        except ValueError as exc:
            raise MalformedOutputError(
                f"Gemini did not return valid JSON for {name}: {exc}"
            ) from exc
        usage = getattr(response, "usage_metadata", None)
        # Thinking is on by default on 2.5 models and those tokens are billed as output.
        output_tokens = (getattr(usage, "candidates_token_count", 0) or 0) + (
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        return StructuredResult(
            value=value,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=output_tokens,
                cache_read_input_tokens=getattr(usage, "cached_content_token_count", 0) or 0,
            ),
        )
