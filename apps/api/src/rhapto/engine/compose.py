from __future__ import annotations

import json

from pydantic import BaseModel, Field

from rhapto.engine.prompts.compose import COMPOSE_RULES
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.engine.scoring import SCORING_KEYS
from rhapto.engine.select import Selection
from rhapto.engine.types import Profile
from rhapto.models.jd_extract import JDExtract
from rhapto.models.profile.tracks import Track
from rhapto.models.resume_document import ResumeBullet, ResumeDocument, ResumeHeader, ResumeSection

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


def build_system_blocks(profile: Profile, track: Track) -> list[SystemBlock]:
    """Cached block = rules + every block in the track's base (stable per track, so cache hits across JDs)."""
    block_map = profile.block_map()
    base = profile.base_for(track)
    blocks_json = json.dumps(
        [
            block_map[bid].model_dump(mode="json", exclude_none=True)
            for bid in base.block_ids
            if bid in block_map
        ],
        indent=1,
    )
    static = f"{COMPOSE_RULES}\n\n<blocks>\n{blocks_json}\n</blocks>"
    dynamic = f"Track: {track.name}. {track.description or ''}".strip()
    return [SystemBlock(text=static, cache=True), SystemBlock(text=dynamic)]


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
        system=build_system_blocks(profile, track),
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


def assemble_resume(output: ComposeOutput, profile: Profile) -> ResumeDocument:
    return ResumeDocument(
        header=build_header(profile.answers), summary=output.summary, sections=output.sections
    )
