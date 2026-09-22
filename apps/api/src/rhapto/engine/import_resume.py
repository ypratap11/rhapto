from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from rhapto.engine.prompts.import_resume import IMPORT_RESUME_SYSTEM
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.profile.blocks import Block
from rhapto.models.source_document import SourceDocument


class ImportedBlock(BaseModel):
    id: str
    type: Literal["role", "project", "achievement", "skill", "credential"]
    org: str | None = None
    role: str | None = None
    period: str | None = None
    content: str
    metric: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImportedTrack(BaseModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
    field: str
    role: str


class ImportedLocation(BaseModel):
    location_home: str | None = None
    location_preferred: list[str] = Field(default_factory=list)
    remote_ok: str | None = None


class ResumeImport(BaseModel):
    """What the model proposes. Nothing here is persisted until the user confirms it."""

    blocks: list[ImportedBlock] = Field(default_factory=list)
    tracks: list[ImportedTrack] = Field(default_factory=list)
    location: ImportedLocation = Field(default_factory=ImportedLocation)


async def import_resume(
    document: SourceDocument, llm: LLMProvider
) -> tuple[ResumeImport, TokenUsage]:
    """One LLM call: a parsed resume to a proposed profile."""
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    if not text.strip():
        raise ValueError("resume is empty")
    result = await llm.complete_structured(
        system=[SystemBlock(text=IMPORT_RESUME_SYSTEM, cache=True)],
        messages=[Message(role="user", content=f"<resume>\n{text}\n</resume>")],
        output_schema=ResumeImport,
        max_tokens=8192,
    )
    return result.value, result.usage


def to_blocks(imported: list[ImportedBlock]) -> list[Block]:
    """Proposal to real `Block`s: never verified, never carrying a guessed date.

    `Block.period` is pattern-validated by the generated model, so an unparseable value is
    detected by trying it and dropping it -- rather than duplicating the regex here, where it
    would drift from the schema.
    """
    out: list[Block] = []
    seen: set[str] = set()
    for item in imported:
        block_id = item.id
        suffix = 2
        while block_id in seen:
            block_id = f"{item.id}-{suffix}"
            suffix += 1
        seen.add(block_id)
        tags = list(item.tags)
        try:
            out.append(
                Block(
                    id=block_id,
                    type=item.type,
                    org=item.org,
                    role=item.role,
                    period=item.period,
                    content=item.content,
                    metric=item.metric,
                    tags=tags,
                    verified=False,
                )
            )
        except ValidationError:
            out.append(
                Block(
                    id=block_id,
                    type=item.type,
                    org=item.org,
                    role=item.role,
                    content=item.content,
                    metric=item.metric,
                    tags=tags,
                    verified=False,
                )
            )
    return out
