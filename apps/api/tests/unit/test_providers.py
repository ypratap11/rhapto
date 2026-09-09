from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.providers.llm import Message, SystemBlock, TokenUsage


class Answer(BaseModel):
    text: str
    score: int


async def test_fake_llm_returns_scripted_responses_in_order() -> None:
    llm = FakeLLMProvider([{"text": "a", "score": 1}, Answer(text="b", score=2)])
    first = await llm.complete_structured(
        system=[SystemBlock(text="sys")],
        messages=[Message(role="user", content="hi")],
        output_schema=Answer,
    )
    second = await llm.complete_structured(system=[], messages=[], output_schema=Answer)
    assert (first.value.text, second.value.text) == ("a", "b")
    assert llm.calls[0].messages[0].content == "hi"
    assert llm.calls[0].output_schema is Answer


async def test_fake_llm_raises_when_exhausted() -> None:
    llm = FakeLLMProvider([])
    with pytest.raises(AssertionError, match="no scripted response"):
        await llm.complete_structured(system=[], messages=[], output_schema=Answer)


async def test_fake_embedder_is_deterministic_and_similarity_aware() -> None:
    embedder = FakeEmbeddingProvider()
    a, b, c = await embedder.embed(
        ["snowflake migration", "snowflake migration program", "pmp certification"]
    )
    assert a == (await embedder.embed(["snowflake migration"]))[0]
    assert len(a) == embedder.dimensions

    def dot(x: list[float], y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True))

    assert dot(a, b) > dot(a, c)


def test_token_usage_adds() -> None:
    total = TokenUsage(input_tokens=1, output_tokens=2) + TokenUsage(
        input_tokens=3, cache_read_input_tokens=4
    )
    assert (total.input_tokens, total.output_tokens, total.cache_read_input_tokens) == (4, 2, 4)


class _FakeMessages:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input={"text": "ok", "score": 9})],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=80,
                cache_creation_input_tokens=0,
            ),
        )


async def test_anthropic_provider_builds_forced_tool_call_with_cache_control() -> None:
    messages = _FakeMessages()
    client = SimpleNamespace(messages=messages)
    provider = AnthropicProvider(model="claude-sonnet-5", client=client)
    result = await provider.complete_structured(
        system=[SystemBlock(text="static", cache=True), SystemBlock(text="dynamic")],
        messages=[Message(role="user", content="go")],
        output_schema=Answer,
        max_tokens=123,
    )
    assert result.value == Answer(text="ok", score=9)
    assert result.usage.cache_read_input_tokens == 80
    kw = messages.kwargs
    assert kw["model"] == "claude-sonnet-5" and kw["max_tokens"] == 123
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in kw["system"][1]
    assert kw["tool_choice"] == {"type": "tool", "name": "emit"}
    assert kw["tools"][0]["input_schema"]["properties"]["score"]["type"] == "integer"
    assert kw["messages"] == [{"role": "user", "content": "go"}]
