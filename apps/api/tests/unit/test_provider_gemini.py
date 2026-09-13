from types import SimpleNamespace
from typing import Any

import pytest
from google import genai
from google.genai import _transformers, errors, types
from pydantic import BaseModel

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.gemini import GeminiProvider
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.tune import TuneOutput
from rhapto.engine.types import EngineError
from rhapto.models.jd_extract import JDExtract

TUNE_JSON = (
    '{"edits": [{"paragraph_id": "p1", "text": "Shipped it", "reason": "keyword"}],'
    ' "cover_note": "hello", "change_log": "one edit", "answers": []}'
)


class _FakeModels:
    def __init__(self, *, text: str | None = TUNE_JSON, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.kwargs: dict[str, Any] = {}

    async def generate_content(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            text=self._text,
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
    # The SDK owns the JSON-Schema -> Gemini conversion: it gets the Pydantic class itself.
    assert config["response_schema"] is TuneOutput


async def test_gemini_omits_system_instruction_when_there_are_no_blocks() -> None:
    models = _FakeModels()
    await _provider(models).complete_structured(
        system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
    )
    assert "system_instruction" not in models.kwargs["config"]


@pytest.mark.parametrize("schema", [JDExtract, ComposeOutput, TuneOutput])
def test_the_sdk_converts_every_engine_schema_without_complaint(schema: type[BaseModel]) -> None:
    """Pins the SDK-owned conversion: `$defs` inlined, optional unions nullable, no forbidden keys."""
    # A real Developer-API client (no network: only its `vertexai` flag is read) so the SDK's
    # unsupported-property check runs, exactly as it does on a live call.
    client = genai.Client(api_key="sk-test")
    converted = _transformers.t_schema(client._api_client, schema)
    assert isinstance(converted, types.Schema)
    assert converted.type == types.Type.OBJECT
    dumped = converted.model_dump(exclude_none=True, mode="json")
    assert "$defs" not in repr(dumped) and "$ref" not in repr(dumped)


def test_the_adapters_config_is_a_valid_generate_content_config() -> None:
    config = {
        "system_instruction": "rules",
        "response_mime_type": "application/json",
        "response_schema": ComposeOutput,
        "max_output_tokens": 4096,
    }
    assert types.GenerateContentConfig.model_validate(config).response_mime_type == (
        "application/json"
    )


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
