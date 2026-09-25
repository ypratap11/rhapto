from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from rhapto.engine.prompts.import_resume import IMPORT_RESUME_SYSTEM
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.profile.blocks import Block
from rhapto.models.source_document import SourceDocument

#: Cap the resume text sent to the LLM. `services.documents.MAX_BYTES` (5 MB) already bounds the
#: upload itself, but a mostly-text document near that cap would still turn into a huge prompt --
#: charged to the user's own key. 40,000 characters is generous for even a long, multi-page CV
#: (a few thousand words) while keeping the worst-case import call's cost bounded and independent
#: of how large a document someone manages to upload.
MAX_RESUME_CHARS = 40_000

_SLUG_PUNCT = re.compile(r"[^a-z0-9]+")


def _slugify(raw: str, *, fallback: str) -> str:
    """`raw` forced into the `^[a-z0-9][a-z0-9-]*$` pattern `Block.id`/`Track.id` require.

    The prompt asks the model for kebab-case ids but nothing enforces it, so `Acme_Lead!` and
    `Acme-Lead` (uppercase is outside the pattern too) are ordinary output. Every run of
    non-`[a-z0-9]` characters becomes a single `-`, leading/trailing `-` are trimmed, and a result
    that is empty (the whole string was punctuation) falls back to `fallback` rather than ever
    letting an invalid id reach a `Block`/`Track` construction.
    """
    slug = _SLUG_PUNCT.sub("-", raw.strip().lower()).strip("-")
    return slug or fallback


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
    text = text[:MAX_RESUME_CHARS]
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

    `id` is pattern-validated too, and unlike `period` there is no "drop the field" fallback for
    an id -- every block needs one. So each id is normalised with `_slugify` *before* the
    de-duplication loop below, meaning a bad id runs through the same uniqueness handling as a
    good one rather than a separate path next to it.
    """
    out: list[Block] = []
    seen: set[str] = set()
    for index, item in enumerate(imported):
        base_id = _slugify(item.id, fallback=f"block-{index + 1}")
        block_id = base_id
        suffix = 2
        while block_id in seen:
            block_id = f"{base_id}-{suffix}"
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


def to_tracks(imported: list[ImportedTrack]) -> list[ImportedTrack]:
    """Proposed tracks with ids forced into `Track.id`'s `^[a-z0-9][a-z0-9-]*$` pattern.

    Mirrors `to_blocks`'s id handling. Taxonomy validity (`field`/`role`) is checked by the
    caller with `services.taxonomy`, which `engine/` may not import -- this only guarantees the
    id is well-formed and unique, so a track surviving the taxonomy filter cannot still 422 the
    `PUT /profile/tracks/{id}` the web app performs on accept, after the blocks are already saved.
    """
    out: list[ImportedTrack] = []
    seen: set[str] = set()
    for index, item in enumerate(imported):
        base_id = _slugify(item.id, fallback=f"track-{index + 1}")
        track_id = base_id
        suffix = 2
        while track_id in seen:
            track_id = f"{base_id}-{suffix}"
            suffix += 1
        seen.add(track_id)
        out.append(item.model_copy(update={"id": track_id}))
    return out
