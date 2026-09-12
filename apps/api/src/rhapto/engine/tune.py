"""Tune mode's LLM step: the user's own resume paragraphs in, a small set of edits out.

Where `compose` writes a resume from the block library, `tune` rewrites the document the user
already has. The model never sees the block library and never emits provenance ids: the only
thing it returns is a list of (paragraph id, new text, reason) triples, which `to_edits` turns
into `Edit`s by reading `before` out of the document itself. That keeps the before/after pair
authoritative on our side -- the model cannot claim a paragraph said something it did not.
"""

from __future__ import annotations

import json
from xml.sax.saxutils import escape, quoteattr

from pydantic import BaseModel, Field

from rhapto.engine.compose import AnswerItem, application_answers
from rhapto.engine.prompts.tune import TUNE_REPAIR_INSTRUCTIONS, TUNE_RULES
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.guardrail_report import GuardrailReport, Violation
from rhapto.models.jd_extract import JDExtract
from rhapto.models.source_document import Edit, SourceDocument

MAX_BULLET_EDITS = 6
MAX_TUNE_TOKENS = 4096


class ProposedEdit(BaseModel):
    """One paragraph rewrite as the model proposes it: the full replacement text, not a diff.

    `before` is deliberately absent -- the document is the source of truth for what the
    paragraph said, so `to_edits` fills it in.
    """

    paragraph_id: str
    text: str
    reason: str


class TuneOutput(BaseModel):
    """Exactly what the LLM returns in tune mode."""

    edits: list[ProposedEdit] = Field(default_factory=list)
    cover_note: str
    change_log: str
    answers: list[AnswerItem] = Field(default_factory=list)

    def answers_dict(self) -> dict[str, str]:
        return {item.key: item.value for item in self.answers}


def _paragraph_line(paragraph_id: str, role: str, section: str | None, text: str) -> str:
    attrs = f"id={quoteattr(paragraph_id)} role={quoteattr(role)}"
    if section:
        attrs += f" section={quoteattr(section)}"
    return f"<p {attrs}>{escape(text)}</p>"


def build_tune_system_blocks(doc: SourceDocument) -> list[SystemBlock]:
    """One cached block: the rules plus the whole document.

    Both halves are stable for as long as the user keeps uploading the same resume, so the
    whole block is cacheable and every JD the user tunes against reuses it. Empty paragraphs
    are skipped -- they exist in the model only to keep paragraph ids index-stable against the
    DOCX, and listing them would just spend tokens inviting the model to edit blank lines.
    """
    lines = [
        _paragraph_line(p.id, p.role, p.section, p.text) for p in doc.paragraphs if p.text.strip()
    ]
    document = "\n".join(lines)
    return [SystemBlock(text=f"{TUNE_RULES}\n\n<document>\n{document}\n</document>", cache=True)]


def build_tune_user_message(
    extract: JDExtract,
    answers: dict[str, str],
    feedback: str | None = None,
    previous_edits: list[Edit] | None = None,
) -> str:
    """The per-job half of the prompt.

    Header answers (name, email, phone, location, links) are stripped by `application_answers`
    because they are not application questions -- the tuner has nothing to draft for them. This
    is not a privacy measure: the document in the cached system block carries the user's real
    contact paragraph, which the tuner needs in order to leave it alone.
    """
    parts = [
        f"<job>\n{extract.model_dump_json(indent=1)}\n</job>",
        f"<answers>\n{json.dumps(application_answers(answers), indent=1)}\n</answers>",
    ]
    if previous_edits:
        dumped = json.dumps([e.model_dump(mode="json") for e in previous_edits], indent=1)
        parts.append(f"<previous_edits>\n{dumped}\n</previous_edits>")
    if feedback:
        parts.append(f"<feedback>\n{feedback.strip()}\n</feedback>")
    return "\n\n".join(parts)


async def tune(
    extract: JDExtract,
    doc: SourceDocument,
    answers: dict[str, str],
    llm: LLMProvider,
    feedback: str | None = None,
    previous_edits: list[Edit] | None = None,
) -> tuple[TuneOutput, TokenUsage]:
    """LLM call 2 in tune mode: the user's document + JD extract to a small set of paragraph edits."""
    result = await llm.complete_structured(
        system=build_tune_system_blocks(doc),
        messages=[
            Message(
                role="user",
                content=build_tune_user_message(extract, answers, feedback, previous_edits),
            )
        ],
        output_schema=TuneOutput,
        max_tokens=MAX_TUNE_TOKENS,
    )
    return result.value, result.usage


def _violation_line(violation: Violation) -> str:
    """One violation as the repair model sees it: the path *and* the paragraph it names.

    `violation.path` indexes the materialised `to_edits` list, which drops no-op proposals, so the
    same index in the model's own `<previous_output>` can be a different proposal entirely. The
    paragraph id is the one identifier both lists agree on, so it goes in the line too.
    """
    where = f"{violation.path} ({violation.block_id})" if violation.block_id else violation.path
    return f"- {where} [{violation.rule}]: {violation.message}"


async def tune_repair(
    previous: TuneOutput,
    report: GuardrailReport,
    system: list[SystemBlock],
    llm: LLMProvider,
) -> tuple[TuneOutput, TokenUsage]:
    """LLM call 3 in tune mode: one retry with the violations spelled out, same cached system blocks."""
    violations = "\n".join(_violation_line(v) for v in report.violations)
    content = (
        f"{TUNE_REPAIR_INSTRUCTIONS}\n\n<previous_output>\n{previous.model_dump_json(indent=1)}\n"
        f"</previous_output>\n\n<violations>\n{violations}\n</violations>"
    )
    result = await llm.complete_structured(
        system=system,
        messages=[Message(role="user", content=content)],
        output_schema=TuneOutput,
        max_tokens=MAX_TUNE_TOKENS,
    )
    return result.value, result.usage


def to_edits(doc: SourceDocument, output: TuneOutput) -> list[Edit]:
    """Materialise the model's proposals against the document.

    `before` comes from the document, never from the model. Edits that do not change the
    paragraph (including whitespace-only changes) are dropped so the writer touches as few
    runs as possible and the change log stays honest. An edit naming a paragraph that does
    not exist is kept with an empty `before` so `tune-scope` can report it instead of it
    disappearing silently.

    Two proposals for one paragraph are collapsed to the last one, because that is the only one
    `apply_edits` and `render_tuned_docx` would keep. Letting both through meant a rewrite that
    never reaches the document could still trip a guardrail, count against the six-bullet limit,
    and show the reviewer two conflicting versions of one line.
    """
    originals = {p.id: p.text for p in doc.paragraphs}
    edits: list[Edit] = []
    for proposed in output.edits:
        before = originals.get(proposed.paragraph_id)
        after = proposed.text.strip()
        if before is not None and after == before.strip():
            continue
        edits.append(
            Edit(
                paragraph_id=proposed.paragraph_id,
                before=before or "",
                after=after,
                reason=proposed.reason,
            )
        )
    last = {edit.paragraph_id: i for i, edit in enumerate(edits)}
    return [edit for i, edit in enumerate(edits) if last[edit.paragraph_id] == i]
