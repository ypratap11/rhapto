from __future__ import annotations

from typing import Any

from rhapto.engine.providers.llm import Message, StructuredResult, SystemBlock, T, TokenUsage

TOOL_NAME = "emit"


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
        tool = {
            "name": TOOL_NAME,
            "description": f"Return the {output_schema.__name__} exactly as specified by the schema.",
            "input_schema": output_schema.model_json_schema(),
        }
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=self._system_payload(system),
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME},
        )
        tool_use = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"), None
        )
        if tool_use is None:
            raise RuntimeError("Anthropic response contained no tool_use block")
        usage = response.usage
        return StructuredResult(
            value=output_schema.model_validate(tool_use.input),
            usage=TokenUsage(
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            ),
        )
