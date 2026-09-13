from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.providers.openai import OpenAIProvider
from rhapto.models.jd_extract import JDExtract

EXTRACT = JDExtract(company="Acme", title="Staff PM", must_have=["python"])


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=30,
        prompt_tokens_details=SimpleNamespace(cached_tokens=64),
    )


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/x"))


class _FakeCompletions:
    """Stands in for ``client.chat.completions``; records the kwargs the adapter sent."""

    def __init__(
        self,
        *,
        parsed: Any = EXTRACT,
        refusal: str | None = None,
        error: Exception | None = None,
        usage: Any = None,
    ) -> None:
        self._parsed = parsed
        self._refusal = refusal
        self._error = error
        self._usage = usage
        self.kwargs: dict[str, Any] = {}

    async def parse(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        message = SimpleNamespace(parsed=self._parsed, refusal=self._refusal)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self._usage)


def _provider(completions: _FakeCompletions, model: str = "gpt-5") -> OpenAIProvider:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIProvider(model=model, client=client)


async def test_openai_returns_the_parsed_value_and_usage() -> None:
    completions = _FakeCompletions(usage=_usage())
    result = await _provider(completions).complete_structured(
        system=[SystemBlock(text="rules", cache=True), SystemBlock(text="blocks")],
        messages=[Message(role="user", content="go"), Message(role="assistant", content="ok")],
        output_schema=JDExtract,
        max_tokens=321,
    )
    assert result.value == EXTRACT
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 30)
    assert result.usage.cache_read_input_tokens == 64
    kw = completions.kwargs
    assert kw["model"] == "gpt-5" and kw["max_tokens"] == 321
    assert kw["response_format"] is JDExtract
    assert kw["messages"] == [
        {"role": "system", "content": "rules\n\nblocks"},
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "ok"},
    ]


async def test_openai_omits_the_system_message_when_there_are_no_blocks() -> None:
    completions = _FakeCompletions()
    await _provider(completions).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
    )
    assert completions.kwargs["messages"] == [{"role": "user", "content": "go"}]


async def test_openai_reports_zero_usage_when_the_response_has_none() -> None:
    result = await _provider(_FakeCompletions()).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
    )
    assert result.usage.input_tokens == 0 and result.usage.cache_read_input_tokens == 0


async def test_openai_refusal_is_malformed_output() -> None:
    provider = _provider(_FakeCompletions(parsed=None, refusal="I cannot help with that"))
    with pytest.raises(MalformedOutputError, match="cannot help"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


async def test_openai_missing_parsed_value_is_malformed_output() -> None:
    provider = _provider(_FakeCompletions(parsed=None))
    with pytest.raises(MalformedOutputError, match="JDExtract"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


@pytest.mark.parametrize(
    "error",
    [
        openai.AuthenticationError(
            "Incorrect API key provided", response=_response(401), body=None
        ),
        openai.PermissionDeniedError(
            "Project does not have access", response=_response(403), body=None
        ),
        openai.RateLimitError(
            "You exceeded your current quota, check your plan and billing details",
            response=_response(429),
            body=None,
        ),
    ],
)
async def test_openai_auth_failures_become_provider_auth_error(error: Exception) -> None:
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
    assert excinfo.value.provider == "openai"
    assert str(error) in str(excinfo.value)


async def test_openai_plain_rate_limit_is_not_an_auth_error() -> None:
    error = openai.RateLimitError(
        "Rate limit reached for gpt-5, try again in 2s", response=_response(429), body=None
    )
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(openai.RateLimitError):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
