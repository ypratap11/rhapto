from __future__ import annotations

import math
import re
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from rhapto.engine.providers.llm import Message, StructuredResult, SystemBlock, T, TokenUsage


@dataclass
class FakeCall:
    system: list[SystemBlock]
    messages: list[Message]
    output_schema: type[BaseModel]


@dataclass
class FakeLLMProvider:
    """Returns scripted responses in order and records every call."""

    responses: Sequence[BaseModel | dict[str, Any]]
    calls: list[FakeCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._queue = list(self.responses)

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        if not self._queue:
            raise AssertionError("FakeLLMProvider: no scripted response left")
        raw = self._queue.pop(0)
        payload = raw if isinstance(raw, dict) else raw.model_dump(mode="json")
        value = output_schema.model_validate(payload)
        self.calls.append(
            FakeCall(system=list(system), messages=list(messages), output_schema=output_schema)
        )
        return StructuredResult(value=value, usage=TokenUsage(input_tokens=10, output_tokens=5))


class FakeEmbeddingProvider:
    """Deterministic hashed bag-of-words vectors: similar texts get similar vectors."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimensions
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vec[zlib.crc32(word.encode()) % self.dimensions] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out
