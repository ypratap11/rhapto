from __future__ import annotations

from pydantic import BaseModel, Field

from rhapto.models.package import ApplicationPackage
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry


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
    jd_text: str
    track_id: str | None = None
    feedback: str | None = None
    previous_package: ApplicationPackage | None = None
