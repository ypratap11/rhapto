from __future__ import annotations

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.guardrail_report import GuardrailReport

REPAIR_INSTRUCTIONS = """Your previous output violated the guardrails listed in <violations>. Return the complete
corrected output. Fix every violation: remove any number you cannot source verbatim from the cited block, restore
exact organisation names, titles, and periods, add missing attribution phrases, and drop bullets whose block is
not allowed. Do not introduce new block ids."""


async def repair(
    previous: ComposeOutput,
    report: GuardrailReport,
    system: list[SystemBlock],
    llm: LLMProvider,
) -> tuple[ComposeOutput, TokenUsage]:
    """LLM call 3: one retry with the violations spelled out. Uses the same cached system blocks as compose."""
    violations = "\n".join(f"- {v.path} [{v.rule}]: {v.message}" for v in report.violations)
    content = (
        f"{REPAIR_INSTRUCTIONS}\n\n<previous_output>\n{previous.model_dump_json(indent=1)}\n</previous_output>"
        f"\n\n<violations>\n{violations}\n</violations>"
    )
    result = await llm.complete_structured(
        system=system,
        messages=[Message(role="user", content=content)],
        output_schema=ComposeOutput,
        max_tokens=8192,
    )
    return result.value, result.usage
