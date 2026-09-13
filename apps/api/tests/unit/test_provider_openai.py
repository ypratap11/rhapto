from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from openai.lib._parsing._completions import type_to_response_format_param
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.providers.openai import OpenAIProvider
from rhapto.engine.tune import TuneOutput
from rhapto.engine.types import EngineError
from rhapto.models.jd_extract import JDExtract

EXTRACT = JDExtract(company="Acme", title="Staff PM", must_have=["python"])


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        prompt_tokens=120,
        completion_tokens=30,
        prompt_tokens_details=SimpleNamespace(cached_tokens=64),
    )


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=httpx2.Request("POST", "https://api.openai.com/v1/x"))


def _status_error(cls: type[openai.APIStatusError], status: int, message: str, **body: str) -> Any:
    """Build an SDK error the way the client does: `body` is the inner `error` object."""
    return cls(message, response=_response(status), body=dict(body) or None)


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
    assert kw["model"] == "gpt-5"
    assert kw["response_format"] is JDExtract
    assert kw["messages"] == [
        {"role": "system", "content": "rules\n\nblocks"},
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "ok"},
    ]


async def test_openai_sends_max_completion_tokens_not_the_deprecated_max_tokens() -> None:
    """`max_tokens` is rejected by the reasoning models the registry offers (gpt-5, gpt-5-mini)."""
    completions = _FakeCompletions()
    await _provider(completions).complete_structured(
        system=[],
        messages=[Message(role="user", content="go")],
        output_schema=JDExtract,
        max_tokens=321,
    )
    assert completions.kwargs["max_completion_tokens"] == 321
    assert "max_tokens" not in completions.kwargs


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
    ("error", "expected"),
    [
        (
            openai.LengthFinishReasonError(completion=ChatCompletion.model_construct(usage=None)),
            "token cap",
        ),
        (openai.ContentFilterFinishReasonError(), "content filter"),
    ],
)
async def test_openai_truncation_and_content_filter_are_retryable_malformed_output(
    error: Exception, expected: str
) -> None:
    """`parse` raises these instead of returning a choice; the pipeline retries MalformedOutputError."""
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(MalformedOutputError, match=expected):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


@pytest.mark.parametrize(
    "error",
    [
        _status_error(openai.AuthenticationError, 401, "Incorrect API key provided"),
        _status_error(openai.PermissionDeniedError, 403, "Project does not have access"),
        _status_error(
            openai.RateLimitError,
            429,
            "You exceeded your current quota",
            code="insufficient_quota",
            type="insufficient_quota",
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


@pytest.mark.parametrize(
    "error",
    [
        _status_error(
            openai.RateLimitError,
            429,
            "Rate limit reached for gpt-5. Add a payment method at .../account/billing",
            code="rate_limit_exceeded",
        ),
        _status_error(openai.InternalServerError, 503, "The server is overloaded"),
        _status_error(openai.BadRequestError, 400, "Unsupported parameter"),
        openai.APITimeoutError(request=httpx2.Request("POST", "https://api.openai.com/v1/x")),
        openai.APIConnectionError(
            request=httpx2.Request("POST", "https://api.openai.com/v1/x"),
        ),
    ],
)
async def test_openai_other_sdk_failures_become_plain_engine_errors(error: Exception) -> None:
    """No raw SDK exception may reach the pipeline, and a retryable limit is not a key problem."""
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(EngineError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
    assert not isinstance(excinfo.value, ProviderAuthError | MalformedOutputError)
    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize("schema", [JDExtract, ComposeOutput, TuneOutput])
def test_engine_schemas_convert_to_a_strict_openai_response_format(schema: type[BaseModel]) -> None:
    """The SDK rewrites `required` to every property and forbids extras; defaulted fields are fine."""
    param = type_to_response_format_param(schema)
    assert isinstance(param, dict)
    json_schema = param["json_schema"]
    assert json_schema["strict"] is True
    body = json_schema["schema"]
    assert body["additionalProperties"] is False
    assert set(body["required"]) == set(body["properties"])
