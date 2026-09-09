import pytest

from rhapto.engine.extract import extract
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.models.jd_extract import JDExtract

JD = (
    "ExampleCo is hiring a Data Platform Program Manager. Must have Snowflake migration experience."
)


async def test_extract_returns_structured_requirements() -> None:
    llm = FakeLLMProvider(
        [
            {
                "company": "ExampleCo",
                "title": "Data Platform Program Manager",
                "must_have": ["Snowflake migration"],
                "keywords": ["Snowflake", "data platform"],
            }
        ]
    )
    result, usage = await extract(JD, llm)
    assert isinstance(result, JDExtract)
    assert result.must_have == ["Snowflake migration"]
    assert usage.input_tokens == 10
    call = llm.calls[0]
    assert call.output_schema is JDExtract
    assert call.system[0].cache is True
    assert JD in call.messages[0].content


async def test_extract_rejects_empty_jd() -> None:
    with pytest.raises(ValueError, match="empty"):
        await extract("   ", FakeLLMProvider([]))
