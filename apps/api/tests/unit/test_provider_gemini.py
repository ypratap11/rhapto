from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import BaseModel

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.gemini import GeminiProvider, schema_for_gemini
from rhapto.engine.providers.llm import MalformedOutputError, Message, SystemBlock
from rhapto.engine.tune import TuneOutput
from rhapto.models.jd_extract import JDExtract

# Keys Gemini's response_schema dialect rejects (or silently ignores) and schema_for_gemini removes.
FORBIDDEN = {"$ref", "$defs", "$schema", "additionalProperties", "title", "default", "allOf"}

TUNE_JSON = (
    '{"edits": [{"paragraph_id": "p1", "text": "Shipped it", "reason": "keyword"}],'
    ' "cover_note": "hello", "change_log": "one edit", "answers": []}'
)


def _assert_clean(node: Any, path: str = "") -> None:
    """Walk a converted schema; inside ``properties`` the keys are field names, not keywords."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties":
                assert isinstance(value, dict), path
                for name, sub in value.items():
                    _assert_clean(sub, f"{path}.properties.{name}")
                continue
            assert key not in FORBIDDEN, f"{path}.{key} survived the conversion"
            _assert_clean(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _assert_clean(item, f"{path}[{index}]")


@pytest.mark.parametrize("model", [JDExtract, ComposeOutput, TuneOutput])
def test_schema_for_gemini_drops_refs_titles_and_extras(model: type[BaseModel]) -> None:
    _assert_clean(schema_for_gemini(model))


def test_schema_for_gemini_inlines_defs_and_keeps_the_useful_keywords() -> None:
    schema = schema_for_gemini(ComposeOutput)
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"sections", "cover_note", "change_log"}
    section = schema["properties"]["sections"]["items"]
    assert section["type"] == "object"
    assert section["properties"]["kind"]["enum"] == [
        "experience",
        "projects",
        "skills",
        "credentials",
    ]
    # A field literally named "title" is data, not the JSON Schema annotation: it must survive.
    assert section["properties"]["title"]["type"] == "string"
    entry = section["properties"]["entries"]["items"]
    assert entry["properties"]["bullets"]["items"]["properties"]["source_block_id"] == {
        "type": "string"
    }
    assert entry["required"] == ["source_block_id"]


def test_schema_for_gemini_turns_optional_fields_into_nullable() -> None:
    entry = schema_for_gemini(ComposeOutput)["properties"]["sections"]["items"]["properties"][
        "entries"
    ]["items"]
    assert entry["properties"]["org"] == {"type": "string", "nullable": True}
    assert entry["properties"]["title"] == {"type": "string", "nullable": True}


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
                cached_content_token_count=150,
            ),
        )


def _provider(models: _FakeModels, model: str = "gemini-2.5-pro") -> GeminiProvider:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiProvider(model=model, client=client)


async def test_gemini_parses_the_json_response_and_reports_usage() -> None:
    models = _FakeModels()
    result = await _provider(models).complete_structured(
        system=[SystemBlock(text="rules", cache=True), SystemBlock(text="doc")],
        messages=[Message(role="user", content="go"), Message(role="assistant", content="ok")],
        output_schema=TuneOutput,
        max_tokens=555,
    )
    assert result.value.edits[0].paragraph_id == "p1"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (200, 40)
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
    assert config["response_schema"] == schema_for_gemini(TuneOutput)


@pytest.mark.parametrize("text", ["not json at all", '{"edits": 3}', "", None])
async def test_gemini_unusable_text_is_malformed_output(text: str | None) -> None:
    provider = _provider(_FakeModels(text=text))
    with pytest.raises(MalformedOutputError, match="TuneOutput"):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (401, "API key not valid. Please pass a valid API key."),
        (403, "Permission denied on resource project."),
        (429, "Quota exceeded for quota metric 'Generate requests'"),
    ],
)
async def test_gemini_auth_failures_become_provider_auth_error(code: int, message: str) -> None:
    error = errors.ClientError(code, {"error": {"code": code, "message": message}})
    provider = _provider(_FakeModels(error=error))
    with pytest.raises(ProviderAuthError) as excinfo:
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
    assert excinfo.value.provider == "gemini"
    assert message in str(excinfo.value)


async def test_gemini_other_client_errors_propagate() -> None:
    error = errors.ClientError(400, {"error": {"code": 400, "message": "bad request"}})
    provider = _provider(_FakeModels(error=error))
    with pytest.raises(errors.ClientError):
        await provider.complete_structured(
            system=[], messages=[Message(role="user", content="go")], output_schema=TuneOutput
        )
