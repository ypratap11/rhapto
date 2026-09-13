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
    status = str(getattr(exc, "status", None) or "")
    lowered = message.lower()
    if code in (401, 403) or any(marker in lowered for marker in _INVALID_KEY_MARKERS):
        return ProviderAuthError(PROVIDER_ID, message)
    if code == 429 and (mentions_quota(message) or status.upper() == "RESOURCE_EXHAUSTED"):
        return ProviderAuthError(PROVIDER_ID, message)
    return EngineError(message)


class GeminiProvider:
    """Structured output via `response_mime_type=application/json` plus a `response_schema`.

    The schema is the Pydantic class itself: `google-genai` converts it (inlining `$defs`, turning
    optional unions into `nullable`, a single-value `Literal` into an `enum`) into the OpenAPI
    dialect Gemini wants, so this adapter deliberately owns no schema translation of its own.

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
            "response_schema": output_schema,
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
        text = response.text
        if not text:
            raise MalformedOutputError(
                f"Gemini returned no text for {output_schema.__name__} "
                "(the response was empty or blocked)"
            )
        try:
            value = output_schema.model_validate_json(text)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"{output_schema.__name__} did not match the schema: "
                f"{exc.error_count()} validation error(s)"
            ) from exc
        except ValueError as exc:
            raise MalformedOutputError(
                f"Gemini did not return valid JSON for {output_schema.__name__}: {exc}"
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
