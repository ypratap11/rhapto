from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from openai.types.chat import ChatCompletion
from pydantic import BaseModel

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.providers.openai import OpenAIProvider, _strict_schema
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
    """Stands in for ``client.chat.completions``; records the kwargs the adapter sent.

    ``create``, not ``parse``: the adapter builds the strict ``json_schema`` response format itself
    and parses the JSON back, so the fake returns raw content the way the API does."""

    def __init__(
        self,
        *,
        content: str | None = None,
        refusal: str | None = None,
        error: Exception | None = None,
        usage: Any = None,
        finish_reason: str | None = "stop",
    ) -> None:
        self._content = EXTRACT.model_dump_json() if content is None else content
        self._refusal = refusal
        self._error = error
        self._usage = usage
        self._finish_reason = finish_reason
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        message = SimpleNamespace(content=self._content, refusal=self._refusal)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=self._finish_reason)],
            usage=self._usage,
        )


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
    response_format = kw["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "JDExtract"
    assert response_format["json_schema"]["strict"] is True
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
    provider = _provider(_FakeCompletions(content="", refusal="I cannot help with that"))
    with pytest.raises(MalformedOutputError, match="cannot help"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


async def test_openai_empty_content_is_malformed_output() -> None:
    provider = _provider(_FakeCompletions(content=""))
    with pytest.raises(MalformedOutputError, match="no content for JDExtract"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


@pytest.mark.parametrize("content", ["not json at all", "{}", '{"company": 4}', "[]"])
async def test_openai_content_that_is_not_the_schema_is_malformed_output(content: str) -> None:
    """Strict mode should make this impossible; the pipeline still gets a retryable error if not."""
    provider = _provider(_FakeCompletions(content=content))
    with pytest.raises(MalformedOutputError, match="not a valid JDExtract"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )


async def test_openai_parses_a_tune_output_the_model_returned() -> None:
    """A full pipeline schema, not just the small one: nested lists and all."""
    expected = TuneOutput(edits=[], cover_note="hello", change_log="nothing", answers=[])
    completions = _FakeCompletions(content=expected.model_dump_json())
    result = await _provider(completions).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
    )
    assert result.value == expected
    assert completions.kwargs["response_format"]["json_schema"]["name"] == "TuneOutput"


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [("length", "token cap"), ("content_filter", "content filter")],
)
async def test_openai_finish_reasons_are_retryable_malformed_output(
    finish_reason: str, expected: str
) -> None:
    """`create` reports these on the choice rather than raising, so the adapter maps them itself."""
    provider = _provider(_FakeCompletions(finish_reason=finish_reason))
    with pytest.raises(MalformedOutputError, match=expected):
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


async def test_openai_insufficient_quota_is_kind_quota() -> None:
    error = _status_error(
        openai.RateLimitError,
        429,
        "You exceeded your current quota",
        code="insufficient_quota",
        type="insufficient_quota",
    )
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
    assert excinfo.value.kind == "quota"


async def test_openai_401_is_kind_auth() -> None:
    error = _status_error(openai.AuthenticationError, 401, "Incorrect API key provided")
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
    assert excinfo.value.kind == "auth"


async def test_openai_402_out_of_credit_is_kind_quota() -> None:
    # OpenRouter signals exhausted credit with HTTP 402; the SDK has no class for it (a bare APIStatusError).
    error = _status_error(openai.APIStatusError, 402, "This request requires more credits")
    provider = _provider(_FakeCompletions(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=JDExtract
        )
    assert excinfo.value.kind == "quota"


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


_NAME_MAPS = {"properties", "$defs", "definitions"}


def _objects(node: Any) -> list[dict[str, Any]]:
    """Every JSON Schema object node in `node`, including the root."""
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_objects(item))
        return found
    if not isinstance(node, dict):
        return found
    if node.get("type") == "object":
        found.append(node)
    for key, value in node.items():
        if key in _NAME_MAPS and isinstance(value, dict):
            for sub in value.values():
                found.extend(_objects(sub))
        else:
            found.extend(_objects(value))
    return found


def _keywords(node: Any) -> set[str]:
    """Every *schema keyword* in `node` — the keys under `properties`/`$defs` are names, not
    keywords, so they are skipped (JDExtract has a field called `title`)."""
    if isinstance(node, list):
        return {k for item in node for k in _keywords(item)}
    if not isinstance(node, dict):
        return set()
    found = set(node)
    for key, value in node.items():
        if key in _NAME_MAPS and isinstance(value, dict):
            for sub in value.values():
                found |= _keywords(sub)
        else:
            found |= _keywords(value)
    return found


@pytest.mark.parametrize("schema", [JDExtract, ComposeOutput, TuneOutput])
def test_engine_schemas_convert_to_a_strict_openai_response_format(schema: type[BaseModel]) -> None:
    """Every property required, no extras at any depth, and no `default` anywhere.

    `default` is the keyword the SDK's converter leaves behind and OpenAI's strict validator does
    not document; the engine's schemas are full of defaulted fields, so a rejection would land on a
    user's first real tailoring run rather than here."""
    body = _strict_schema(schema)
    keywords = _keywords(body)
    assert "default" not in keywords
    assert "title" not in keywords
    nodes = _objects(body)
    assert len(nodes) >= 1
    for node in nodes:
        assert node["additionalProperties"] is False, node
        assert set(node["required"]) == set(node["properties"]), node


def test_the_strict_schema_keeps_a_property_named_like_a_dropped_keyword() -> None:
    """`title` is both a schema keyword and a JDExtract field; only the keyword may go."""
    body = _strict_schema(JDExtract)
    assert "title" in body["properties"]
    assert "title" not in body
    assert "title" not in body["properties"]["title"]
