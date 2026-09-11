from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from rhapto.engine.types import Profile, ProfileError
from rhapto.models.profile.answers import AnswersFile
from rhapto.models.profile.bases import BasesFile, ResumeBase
from rhapto.models.profile.blocks import Block, BlocksFile
from rhapto.models.profile.guardrails import GuardrailRule, GuardrailsFile
from rhapto.models.profile.tracks import Track, TracksFile
from rhapto.models.profile.watchlist import WatchlistFile

DEFAULT_RULES = [
    "no-unverified-metrics",
    "no-invented-entities",
    "date-consistency",
    "attribution",
    "visibility-context",
]


def _read[M: BaseModel](path: Path, model: type[M]) -> M | None:
    if not path.exists():
        return None
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return model.model_validate(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise ProfileError(f"{path.name}: {exc}") from exc


def _require[M: BaseModel](path: Path, model: type[M]) -> M:
    loaded = _read(path, model)
    if loaded is None:
        raise ProfileError(f"{path.name} not found in {path.parent}")
    return loaded


def default_guardrails() -> list[GuardrailRule]:
    return [GuardrailRule(rule=rule) for rule in DEFAULT_RULES]


def synthesize_bases(tracks: list[Track], blocks: list[Block]) -> list[ResumeBase]:
    """One base per distinct track.resume_base containing every block, in library order."""
    seen: dict[str, ResumeBase] = {}
    for track in tracks:
        if track.resume_base not in seen:
            seen[track.resume_base] = ResumeBase(
                id=track.resume_base,
                name=f"{track.name} (all blocks)",
                block_ids=[b.id for b in blocks],
            )
    return list(seen.values())


def load_profile(path: Path) -> Profile:
    path = Path(path)
    blocks = _require(path / "blocks.yaml", BlocksFile).blocks
    tracks = _require(path / "tracks.yaml", TracksFile).tracks
    ids = [b.id for b in blocks]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ProfileError(f"blocks.yaml: duplicate block id(s): {', '.join(dupes)}")

    bases_file = _read(path / "bases.yaml", BasesFile)
    bases = bases_file.bases if bases_file else synthesize_bases(tracks, blocks)
    known = set(ids)
    for base in bases:
        missing = [bid for bid in base.block_ids if bid not in known]
        if missing:
            raise ProfileError(
                f"bases.yaml: base {base.id} references unknown block(s): {', '.join(missing)}"
            )
    base_ids = {b.id for b in bases}
    for track in tracks:
        if track.resume_base not in base_ids:
            raise ProfileError(
                f"tracks.yaml: track {track.id} references unknown base {track.resume_base}"
            )

    guardrails_file = _read(path / "guardrails.yaml", GuardrailsFile)
    answers_file = _read(path / "answers.yaml", AnswersFile)
    watchlist_file = _read(path / "watchlist.yaml", WatchlistFile)
    return Profile(
        blocks=blocks,
        tracks=tracks,
        bases=bases,
        guardrails=guardrails_file.guardrails if guardrails_file else default_guardrails(),
        answers=answers_file.answers if answers_file else {},
        watchlist=watchlist_file.watchlist if watchlist_file else [],
        aggregators=watchlist_file.aggregators if watchlist_file else [],
    )


def _write(path: Path, payload: BaseModel) -> None:
    path.write_text(
        yaml.safe_dump(
            payload.model_dump(mode="json", exclude_none=True), sort_keys=False, allow_unicode=True
        ),
        encoding="utf-8",
    )


def dump_profile(profile: Profile, path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    _write(path / "blocks.yaml", BlocksFile(blocks=profile.blocks))
    _write(path / "tracks.yaml", TracksFile(tracks=profile.tracks))
    _write(path / "bases.yaml", BasesFile(bases=profile.bases))
    _write(path / "guardrails.yaml", GuardrailsFile(guardrails=profile.guardrails))
    _write(path / "answers.yaml", AnswersFile(answers=profile.answers))
    _write(
        path / "watchlist.yaml",
        WatchlistFile(watchlist=profile.watchlist, aggregators=profile.aggregators),
    )
