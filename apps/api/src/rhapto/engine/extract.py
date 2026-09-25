from __future__ import annotations

from rhapto.engine.prompts.extract import EXTRACT_SYSTEM
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.jd_extract import JDExtract


async def extract(jd_text: str, llm: LLMProvider) -> tuple[JDExtract, TokenUsage]:
    """LLM call 1: job description text to structured requirements."""
    if not jd_text.strip():
        raise ValueError("job description is empty")
    result = await llm.complete_structured(
        system=[SystemBlock(text=EXTRACT_SYSTEM, cache=True)],
        messages=[
            Message(
                role="user", content=f"<job_description>\n{jd_text.strip()}\n</job_description>"
            )
        ],
        output_schema=JDExtract,
        max_tokens=8192,  # headroom for a model that reasons before answering
    )
    return result.value, result.usage
