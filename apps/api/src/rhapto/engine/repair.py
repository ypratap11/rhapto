from __future__ import annotations

from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.guardrail_report import GuardrailReport

REPAIR_INSTRUCTIONS = """Your previous output violated the guardrails listed in <violations>. Return the complete
corrected output. Fix every violation: remove any number you cannot source verbatim from the cited block, restore
exact organisation names, titles, and periods, and add missing attribution phrases. If a bullet cites a block id
that is not in <blocks>, remove only that bullet -- never the entry it was in, and never the block id itself.

A "completeness" violation names a block that must have exactly one entry in its own section (role -> experience,
project -> projects, credential -> credentials), with org, role/title and period copied verbatim from that
block's fields in <blocks>. Never resolve ANY violation by deleting an entry, a section, or a block id: the
corrected document must keep an entry for every block id it already cites, plus a new entry for every block id
a completeness violation names. If the corrected document would be too long, shorten a low-priority entry to a
single bullet -- never remove the entry. Do not introduce new block ids."""


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
