from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from rhapto.models.jd_extract import JDExtract
from rhapto.models.package import ApplicationPackage
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry, WatchlistEntry
from rhapto.models.source_document import SourceDocument


class EngineError(Exception):
    """Base class for engine failures."""


class ProfileError(EngineError):
    """The profile is missing, malformed, or internally inconsistent."""


class Profile(BaseModel):
    """In-memory profile. Loaded from YAML (CLI) or Postgres (worker); the engine does not care."""

    blocks: list[Block]
    tracks: list[Track]
    bases: list[ResumeBase]
    guardrails: list[GuardrailRule]
    answers: dict[str, str] = Field(default_factory=dict)
    watchlist: list[WatchlistEntry] = Field(default_factory=list)
    aggregators: list[AggregatorEntry] = Field(default_factory=list)

    def block_map(self) -> dict[str, Block]:
        return {b.id: b for b in self.blocks}

    def get_track(self, track_id: str | None) -> Track:
        if not self.tracks:
            raise ProfileError("profile has no tracks")
        if track_id is None:
            return self.tracks[0]
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise ProfileError(f"unknown track: {track_id}")

    def base_for(self, track: Track) -> ResumeBase:
        for base in self.bases:
            if base.id == track.resume_base:
                return base
        raise ProfileError(f"track {track.id} references unknown resume base {track.resume_base}")


class TailorRequest(BaseModel):
    """One tailoring run.

    `mode` picks which pipeline branch runs: "blocks" writes a resume from the block library,
    "tune" rewrites the document the user uploaded. Tune mode needs both halves of that
    document -- the parsed `source_document` the engine reasons about and the original
    `source_docx` bytes the writer edits in place -- so the validator insists on both rather
    than letting the pipeline discover a half-populated request.
    """

    jd_text: str
    # A JD extract the caller already holds, so a regenerate does not spend an LLM call deriving
    # the same result from the same unchanged `jd_text`. None means "extract it".
    jd_extract: JDExtract | None = None
    track_id: str | None = None
    feedback: str | None = None
    previous_package: ApplicationPackage | None = None
    mode: Literal["blocks", "tune"] = "blocks"
    source_document: SourceDocument | None = None
    # The raw upload. Excluded from dumps: the API stores the request dict on a task row, and a
    # multi-megabyte base64 DOCX has no business in a JSON column (or in a log line, or in a
    # repr of a failing request).
    source_docx: bytes | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def _tune_needs_a_document(self) -> TailorRequest:
        if self.mode == "tune" and (self.source_document is None or self.source_docx is None):
            raise ValueError("mode 'tune' requires both source_document and source_docx")
        return self
