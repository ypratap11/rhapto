from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class SystemBlock(BaseModel):
    """A system prompt segment. cache=True marks it for provider-side prompt caching."""

    text: str
    cache: bool = False


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
        )


class MalformedOutputError(RuntimeError):
    """The model answered, but its structured output did not match the requested schema."""


@dataclass(frozen=True)
class StructuredResult(Generic[T]):  # noqa: UP046
    value: T
    usage: TokenUsage


class LLMProvider(Protocol):
    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]: ...
