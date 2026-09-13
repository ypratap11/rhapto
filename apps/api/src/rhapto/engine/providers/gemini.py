from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

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

# Gemini's response_schema is OpenAPI 3.0-flavoured, not JSON Schema: no $ref/$defs, no
# additionalProperties, and nullability is a `nullable` flag rather than a union with "null".
_DROPPED_KEYS = frozenset({"title", "default", "additionalProperties", "$schema", "$defs"})


def schema_for_gemini(model: type[BaseModel]) -> dict[str, Any]:
    """Translate a Pydantic JSON schema into the subset Gemini accepts as `response_schema`."""
    schema = model.model_json_schema()
    return _convert(schema, schema.get("$defs", {}), ())


def _convert(node: dict[str, Any], defs: dict[str, Any], stack: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for source in _inlined(node, defs, stack):
        out.update(source)
    if "anyOf" in node:
        out.update(_convert_union(node["anyOf"], defs, stack))
    for key, value in node.items():
        if key in _DROPPED_KEYS or key in {"$ref", "allOf", "anyOf"}:
            continue
        if key == "properties":
            # The keys here are field names -- only their values are schemas.
            out[key] = {name: _convert(sub, defs, stack) for name, sub in value.items()}
        elif key == "items":
            out[key] = _convert(value, defs, stack)
        else:
            out[key] = list(value) if isinstance(value, list) else value
    return out


def _inlined(
    node: dict[str, Any], defs: dict[str, Any], stack: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Resolve `$ref` (and the single-member `allOf` Pydantic emits beside field metadata)."""
    refs = [node["$ref"]] if "$ref" in node else []
    resolved: list[dict[str, Any]] = []
    for member in node.get("allOf", []):
        if set(member) == {"$ref"}:
            refs.append(member["$ref"])
        else:
            resolved.append(_convert(member, defs, stack))
    for ref in refs:
        name = ref.rsplit("/", 1)[-1]
        if name in stack:
            raise EngineError(f"cannot inline recursive schema {name!r} for Gemini")
        target = defs.get(name)
        if target is None:
            raise EngineError(f"schema reference {ref!r} has no definition")
        resolved.append(_convert(target, defs, (*stack, name)))
    return resolved


def _convert_union(
    variants: list[dict[str, Any]], defs: dict[str, Any], stack: tuple[str, ...]
) -> dict[str, Any]:
    real = [v for v in variants if v.get("type") != "null"]
    out: dict[str, Any] = {"nullable": True} if len(real) < len(variants) else {}
    if len(real) == 1:
        out.update(_convert(real[0], defs, stack))
    elif real:
        out["anyOf"] = [_convert(v, defs, stack) for v in real]
    return out


def _auth_error(exc: BaseException) -> ProviderAuthError | None:
    """Map the SDK's credential failures; the SDK is imported here so the module stays import-light."""
    from google.genai import errors as genai_errors

    if not isinstance(exc, genai_errors.APIError):
        return None
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None) or str(exc)
    if code in (401, 403) or (code == 429 and mentions_quota(message)):
        return ProviderAuthError(PROVIDER_ID, message)
    return None


class GeminiProvider:
    """Structured output via `response_mime_type=application/json` plus a converted response schema.

    Gemini has no per-block cache control (implicit caching applies to long prefixes), so the
    system blocks are joined into one `system_instruction` and `SystemBlock.cache` is advisory.
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
        config = {
            "system_instruction": "\n\n".join(b.text for b in system),
            "response_mime_type": "application/json",
            "response_schema": schema_for_gemini(output_schema),
            "max_output_tokens": max_tokens,
        }
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as exc:
            auth = _auth_error(exc)
            if auth is not None:
                raise auth from exc
            raise
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
        return StructuredResult(
            value=value,
            usage=TokenUsage(
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                cache_read_input_tokens=getattr(usage, "cached_content_token_count", 0) or 0,
            ),
        )
