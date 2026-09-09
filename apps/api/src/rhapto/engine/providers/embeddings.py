from __future__ import annotations

import asyncio
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed. The model is loaded lazily on first use."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dimensions: int = 384) -> None:
        self.model_name = model_name
        self.dimensions = dimensions
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily: heavy dependency

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = await asyncio.to_thread(self._load)
        vectors = await asyncio.to_thread(lambda: list(model.embed(texts)))
        return [[float(x) for x in vec] for vec in vectors]
