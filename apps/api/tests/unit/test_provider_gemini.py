import os
from types import SimpleNamespace
from typing import Any

import pytest
from google import genai
from google.genai import errors, models, types
from pydantic import BaseModel

from rhapto.api.routers.settings import Ping
from rhapto.engine.compose import ComposeOutput
from rhapto.engine.import_resume import ResumeImport
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.gemini import GeminiProvider
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.tune import TuneOutput
from rhapto.engine.types import EngineError
from rhapto.models.jd_extract import JDExtract

#: Every schema the engine (and the Settings connection test) sends through this adapter.
ENGINE_SCHEMAS: list[type[BaseModel]] = [JDExtract, ComposeOutput, TuneOutput, ResumeImport, Ping]

TUNE_JSON = (
    '{"edits": [{"paragraph_id": "p1", "text": "Shipped it", "reason": "keyword"}],'
    ' "cover_note": "hello", "change_log": "one edit", "answers": []}'
)


class _FakeModels:
    def __init__(
        self,
        *,
        text: str | None = TUNE_JSON,
        error: Exception | None = None,
        finish_reason: Any = types.FinishReason.STOP,
    ) -> None:
        self._text = text
        self._error = error
        self._finish_reason = finish_reason
        self.kwargs: dict[str, Any] = {}

    async def generate_content(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            text=self._text,
            candidates=[SimpleNamespace(finish_reason=self._finish_reason)],
            usage_metadata=SimpleNamespace(
                prompt_token_count=200,
                candidates_token_count=40,
                thoughts_token_count=15,
                cached_content_token_count=150,
            ),
        )


def _provider(models: _FakeModels, model: str = "gemini-2.5-pro") -> GeminiProvider:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiProvider(model=model, client=client)


def _client_error(code: int, message: str, status: str | None = None) -> errors.ClientError:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if status is not None:
        body["error"]["status"] = status
    return errors.ClientError(code, body)


async def test_gemini_parses_the_json_response_and_reports_usage() -> None:
    models = _FakeModels()
    result = await _provider(models).complete_structured(
        system=[SystemBlock(text="rules", cache=True), SystemBlock(text="doc")],
        messages=[Message(role="user", content="go"), Message(role="assistant", content="ok")],
        output_schema=TuneOutput,
        max_tokens=555,
    )
    assert result.value.edits[0].paragraph_id == "p1"
    assert result.usage.input_tokens == 200
    # Thinking is on by default on 2.5 models and those tokens are billed as output.
    assert result.usage.output_tokens == 55
    assert result.usage.cache_read_input_tokens == 150
    kw = models.kwargs
    assert kw["model"] == "gemini-2.5-pro"
    assert kw["contents"] == [
        {"role": "user", "parts": [{"text": "go"}]},
        {"role": "model", "parts": [{"text": "ok"}]},
    ]
    config = kw["config"]
    assert config["system_instruction"] == "rules\n\ndoc"
    assert config["response_mime_type"] == "application/json"
    assert config["max_output_tokens"] == 555
    # A plain JSON Schema dict: the SDK forwards it untouched, so a class here would reach the wire
    # unconverted. And never `response_schema` -- see the wire tests below.
    assert isinstance(config["response_json_schema"], dict)
    assert config["response_json_schema"] == TuneOutput.model_json_schema()
    assert "response_schema" not in config


async def test_gemini_omits_system_instruction_when_there_are_no_blocks() -> None:
    models = _FakeModels()
    await _provider(models).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
    )
    assert "system_instruction" not in models.kwargs["config"]


def _wire_config(config: dict[str, Any]) -> str:
    """The generation config exactly as the SDK builds it for the Developer API request body.

    Runs the SDK's own request builder (no network: a real client is needed only for its
    `vertexai` flag), then dumps any SDK model objects the way the request serializer does.
    """
    client = genai.Client(api_key="sk-test")
    wire = models._GenerateContentConfig_to_mldev(client._api_client, config, parent_object={})

    def plain(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return plain(value.model_dump(exclude_none=True, mode="json"))
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [plain(v) for v in value]
        return value

    return repr(plain(wire))


async def _adapter_config(schema: type[BaseModel]) -> dict[str, Any]:
    fake = _FakeModels(text=None)
    with pytest.raises(MalformedOutputError):  # the fake returns no text; only the request matters
        await _provider(fake).complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=schema
        )
    config: dict[str, Any] = fake.kwargs["config"]
    return config


@pytest.mark.parametrize("schema", [JDExtract, ComposeOutput])
def test_the_openapi_response_schema_path_sends_what_the_api_rejects(
    schema: type[BaseModel],
) -> None:
    """Known-bad input, pinned: this is the request that failed live on 2026-09-29 with
    `Unknown name "additional_properties" at 'generation_config.response_schema...'`.

    `extra="forbid"` becomes `additionalProperties: false`; the SDK's local guard only checks that
    value for truthiness, so it forwards it inside `responseSchema`, which the API refuses. If this
    ever stops holding, the SDK changed -- revisit the adapter rather than deleting the test.
    """
    wire = _wire_config({"response_mime_type": "application/json", "response_schema": schema})
    assert "responseSchema" in wire
    assert "additional_properties" in wire


@pytest.mark.parametrize("schema", ENGINE_SCHEMAS)
async def test_the_adapter_sends_every_engine_schema_as_json_schema_on_the_wire(
    schema: type[BaseModel],
) -> None:
    wire = _wire_config(await _adapter_config(schema))
    assert "responseJsonSchema" in wire
    assert "responseSchema" not in wire
    assert "additional_properties" not in wire


@pytest.mark.parametrize("schema", ENGINE_SCHEMAS)
async def test_the_adapters_config_is_a_valid_generate_content_config(
    schema: type[BaseModel],
) -> None:
    config = await _adapter_config(schema)
    validated = types.GenerateContentConfig.model_validate(config)
    assert validated.response_mime_type == "application/json"
    assert validated.response_json_schema == schema.model_json_schema()


@pytest.mark.parametrize(
    ("finish_reason", "match"),
    [
        (types.FinishReason.MAX_TOKENS, "token cap"),
        ("MAX_TOKENS", "token cap"),  # some SDK paths hand back the plain string
        (types.FinishReason.SAFETY, "safety"),
        (types.FinishReason.BLOCKLIST, "safety"),
        (types.FinishReason.PROHIBITED_CONTENT, "safety"),
        (types.FinishReason.SPII, "safety"),
        (types.FinishReason.RECITATION, "recitation"),
    ],
)
async def test_gemini_names_why_it_stopped_early(finish_reason: Any, match: str) -> None:
    """A truncated or filtered answer says so, rather than surfacing as a vague JSON error."""
    provider = _provider(_FakeModels(text='{"edits": [', finish_reason=finish_reason))
    with pytest.raises(MalformedOutputError, match=match):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )


@pytest.mark.parametrize(
    "finish_reason",
    [
        None,
        types.FinishReason.FINISH_REASON_UNSPECIFIED,
        types.FinishReason.OTHER,
        "STOP",
    ],
)
async def test_an_ordinary_or_unknown_finish_reason_with_valid_json_still_parses(
    finish_reason: Any,
) -> None:
    """Only the named early stops are errors; anything else with valid JSON is a normal answer."""
    result = await _provider(_FakeModels(finish_reason=finish_reason)).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
    )
    assert result.value.edits[0].paragraph_id == "p1"


async def test_a_response_without_candidates_still_parses_its_text() -> None:
    models = _FakeModels()
    real = models.generate_content

    async def no_candidates(**kwargs: Any) -> Any:
        response = await real(**kwargs)
        response.candidates = None
        return response

    models.generate_content = no_candidates  # type: ignore[method-assign]
    result = await _provider(models).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
    )
    assert result.value.cover_note == "hello"


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="live Gemini call; set GEMINI_API_KEY (and optionally GEMINI_TEST_MODEL) to run",
)
@pytest.mark.parametrize("schema", ENGINE_SCHEMAS)
async def test_live_gemini_accepts_every_engine_schema(schema: type[BaseModel]) -> None:
    provider = GeminiProvider(
        model=os.environ.get("GEMINI_TEST_MODEL", "gemini-3.7-flash"),
        api_key=os.environ["GEMINI_API_KEY"],
    )
    result = await provider.complete_structured(
        system=[],
        messages=[Message(role="user", content="Return a small, valid example object.")],
        output_schema=schema,
    )
    assert isinstance(result.value, schema)


@pytest.mark.parametrize("text", ["not json at all", '{"edits": 3}', "", None])
async def test_gemini_unusable_text_is_malformed_output(text: str | None) -> None:
    provider = _provider(_FakeModels(text=text))
    with pytest.raises(MalformedOutputError, match="TuneOutput"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )


@pytest.mark.parametrize(
    ("code", "message", "status"),
    [
        # A bad Developer API key is a 400 INVALID_ARGUMENT, not a 401.
        (400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"),
        (401, "Request had invalid authentication credentials.", "UNAUTHENTICATED"),
        (403, "Permission denied on resource project.", "PERMISSION_DENIED"),
        (429, "Quota exceeded for quota metric 'Generate requests'", "RESOURCE_EXHAUSTED"),
    ],
)
async def test_gemini_auth_failures_become_provider_auth_error(
    code: int, message: str, status: str
) -> None:
    error = _client_error(code, message, status)
    provider = _provider(_FakeModels(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
    assert excinfo.value.provider == "gemini"
    assert message in str(excinfo.value)


@pytest.mark.parametrize(
    "error",
    [
        _client_error(400, "Invalid value for max_output_tokens", "INVALID_ARGUMENT"),
        _client_error(404, "models/gemini-2.5-pro is not found", "NOT_FOUND"),
        errors.ServerError(503, {"error": {"code": 503, "message": "The model is overloaded"}}),
        TimeoutError("read timed out"),
    ],
)
async def test_gemini_other_sdk_failures_become_plain_engine_errors(error: Exception) -> None:
    """No raw SDK exception may reach the pipeline, and a transient 5xx is not a key problem."""
    provider = _provider(_FakeModels(error=error))
    with pytest.raises(EngineError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
    assert not isinstance(excinfo.value, ProviderAuthError | MalformedOutputError)
    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize(
    ("code", "message", "status", "kind"),
    [
        (401, "Request had invalid authentication credentials.", "UNAUTHENTICATED", "auth"),
        (400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT", "auth"),
        (429, "Quota exceeded for quota metric 'Generate requests'", "RESOURCE_EXHAUSTED", "quota"),
        (
            429,
            "Your project has exceeded its billing limit. Check your plan and billing details.",
            "RESOURCE_EXHAUSTED",
            "quota",
        ),
    ],
)
async def test_gemini_auth_failure_kind(code: int, message: str, status: str, kind: str) -> None:
    provider = _provider(_FakeModels(error=_client_error(code, message, status)))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
    assert excinfo.value.kind == kind


async def test_gemini_per_minute_rate_limit_is_not_a_key_problem() -> None:
    # Owner ruling: only explicit billing / credit / quota-exceeded signals are "quota". A bare
    # RESOURCE_EXHAUSTED per-minute limit is retryable and keeps the generic path.
    error = _client_error(429, "Rate limit reached. Please retry in 30s.", "RESOURCE_EXHAUSTED")
    provider = _provider(_FakeModels(error=error))
    with pytest.raises(EngineError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
    assert not isinstance(excinfo.value, ProviderAuthError)
