from __future__ import annotations

import json

from pydantic import BaseModel, Field

from rhapto.engine.guardrails.dates import parse_period
from rhapto.engine.prompts.compose import COMPOSE_RULES
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.engine.scoring import SCORING_KEYS
from rhapto.engine.select import Selection
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.tracks import Track
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)

HEADER_KEYS = frozenset({"name", "email", "phone", "location", "links"})


class AnswerItem(BaseModel):
    """One application answer. A list of pairs, not a free-form map: a map field invited the model
    to nest the whole output under it."""

    key: str
    value: str


class ComposeOutput(BaseModel):
    """Exactly what the LLM returns. The header is added deterministically by assemble_resume."""

    summary: list[ResumeBullet] = Field(default_factory=list)
    sections: list[ResumeSection]
    cover_note: str
    change_log: str
    answers: list[AnswerItem] = Field(default_factory=list)

    def answers_dict(self) -> dict[str, str]:
        return {item.key: item.value for item in self.answers}


def build_header(answers: dict[str, str]) -> ResumeHeader:
    links = [s.strip() for s in answers.get("links", "").split(",") if s.strip()]
    return ResumeHeader(
        name=answers.get("name") or "Candidate",
        email=answers.get("email"),
        phone=answers.get("phone"),
        location=answers.get("location"),
        links=links,
    )


def application_answers(answers: dict[str, str]) -> dict[str, str]:
    """Only the answers an employer might actually ask: the resume header fields go through
    `build_header`, and the scoring keys never leave the scorer (`location_home` is contact
    detail besides)."""
    return {k: v for k, v in answers.items() if k not in HEADER_KEYS and k not in SCORING_KEYS}


def build_system_blocks(profile: Profile, track: Track, selection: Selection) -> list[SystemBlock]:
    """Cached block = the rules alone; the uncached block carries the selected blocks and track.

    Only the selected blocks are sent. Provenance permits a bullet to cite nothing else, so any
    block visible here but absent from `selection` is an invitation to produce a package that
    fails validation -- which is what happened while the prompt carried the track's whole base.
    That base was what made this block cacheable per track; the rules are what stay stable now,
    and the blocks move into the dynamic half.
    """
    block_map = profile.block_map()
    blocks_json = json.dumps(
        [
            block_map[bid].model_dump(mode="json", exclude_none=True)
            for bid in selection.block_ids
            if bid in block_map
        ],
        indent=1,
    )
    track_line = f"Track: {track.name}. {track.description or ''}".strip()
    dynamic = f"{track_line}\n\n<blocks>\n{blocks_json}\n</blocks>"
    return [SystemBlock(text=COMPOSE_RULES, cache=True), SystemBlock(text=dynamic)]


def build_user_message(
    extract: JDExtract,
    selection: Selection,
    answers: dict[str, str],
    feedback: str | None = None,
    previous: ResumeDocument | None = None,
) -> str:
    parts = [
        f"<job>\n{extract.model_dump_json(indent=1)}\n</job>",
        f"<selected_block_ids>\n{json.dumps(selection.block_ids)}\n</selected_block_ids>",
        f"<answers>\n{json.dumps(application_answers(answers), indent=1)}\n</answers>",
    ]
    if previous is not None:
        # Name only: email, phone, location and links never reach the LLM, on the fresh path
        # (application_answers strips them) or on regeneration.
        redacted = previous.model_copy(update={"header": ResumeHeader(name=previous.header.name)})
        parts.append(
            f"<previous_resume>\n{redacted.model_dump_json(indent=1, exclude_none=True)}\n</previous_resume>"
        )
    if feedback:
        parts.append(f"<feedback>\n{feedback.strip()}\n</feedback>")
    return "\n\n".join(parts)


async def compose(
    extract: JDExtract,
    profile: Profile,
    track: Track,
    selection: Selection,
    llm: LLMProvider,
    feedback: str | None = None,
    previous: ResumeDocument | None = None,
) -> tuple[ComposeOutput, TokenUsage]:
    """LLM call 2: selected blocks + JD extract to resume sections, cover note, change log, answers."""
    result = await llm.complete_structured(
        system=build_system_blocks(profile, track, selection),
        messages=[
            Message(
                role="user",
                content=build_user_message(extract, selection, profile.answers, feedback, previous),
            )
        ],
        output_schema=ComposeOutput,
        max_tokens=8192,
    )
    return result.value, result.usage


def _experience_sorted(section: ResumeSection, profile: Profile) -> ResumeSection:
    """Experience in resume order: current roles first, then by how recently each ended.

    The composer orders entries by relevance to the job, which is right for Projects and Skills
    and wrong for Experience: on an AI-weighted track a side studio started in 2024 outranked the
    day job held since 2023 and was printed above it. Order is a property of a resume, not a
    judgement call, so it is applied here rather than asked of the model.

    Within the same end date a `concurrent` block sorts after a non-concurrent one, so a side
    venture never displaces the employment it runs alongside -- that flag already exists to tell
    the date rules an overlap is deliberate, and it answers this question too.

    An entry whose period does not parse keeps a stable place at the end: it has no date to sort
    on, and inventing one is what the date rules exist to prevent.
    """
    blocks = profile.block_map()

    def key(item: tuple[int, ResumeEntry]) -> tuple[int, int, int, int]:
        index, entry = item
        parsed = parse_period(entry.period or "")
        if parsed is None:
            return (1, 0, 0, index)
        start, end = parsed
        block = blocks.get(entry.source_block_id or "")
        concurrent = 1 if (block and block.concurrent) else 0
        return (0, -end, concurrent, -start)

    ordered = [entry for _, entry in sorted(enumerate(section.entries), key=key)]
    return section.model_copy(update={"entries": ordered})


def assemble_resume(output: ComposeOutput, profile: Profile) -> ResumeDocument:
    sections = [
        _experience_sorted(s, profile) if s.kind == "experience" else s for s in output.sections
    ]
    return ResumeDocument(
        header=build_header(profile.answers), summary=output.summary, sections=sections
    )
