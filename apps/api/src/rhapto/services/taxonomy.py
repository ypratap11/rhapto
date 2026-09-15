"""The field -> role taxonomy the Tracks picker and the Field filter are built from.

The data lives in `packages/schemas/taxonomy.yaml`, is validated by `packages/schemas/taxonomy.json`
and is read through the generated `models.taxonomy.TaxonomyFile`. `packages/` is not on the runtime
path, so the Docker image copies the file to `/app/schemas/taxonomy.yaml`; `RHAPTO_TAXONOMY_PATH`
overrides both, for tests and for anyone who wants their own list.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from rhapto.engine.types import ProfileError
from rhapto.models.profile.tracks import Track
from rhapto.models.taxonomy import TaxonomyField, TaxonomyFile, TaxonomyRole

#: Where the Docker image puts the file (see apps/api/Dockerfile).
IMAGE_PATH = Path("/app/schemas/taxonomy.yaml")
#: Where it lives in a source checkout: .../apps/api/src/rhapto/services/ -> repo root.
REPO_PATH = Path(__file__).resolve().parents[5] / "packages" / "schemas" / "taxonomy.yaml"

_PUNCT = re.compile(r"[^a-z0-9]+")


class TaxonomyError(Exception):
    """The taxonomy file is missing, unreadable, or does not match its schema."""


def taxonomy_path() -> Path:
    """The file this deployment reads: the env override, then the image, then the checkout."""
    override = os.environ.get("RHAPTO_TAXONOMY_PATH", "").strip()
    if override:
        return Path(override)
    return IMAGE_PATH if IMAGE_PATH.exists() else REPO_PATH


def load_taxonomy(path: Path) -> TaxonomyFile:
    """Parse and validate one taxonomy file. Every failure is a TaxonomyError naming the path."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TaxonomyError(f"cannot read the taxonomy at {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{path} is not valid YAML: {exc}") from exc
    try:
        return TaxonomyFile.model_validate(raw)
    except ValidationError as exc:
        raise TaxonomyError(f"{path} does not match taxonomy.json: {exc}") from exc


@lru_cache(maxsize=1)
def taxonomy() -> TaxonomyFile:
    """The loaded taxonomy. Cached: the file cannot change while the process runs."""
    return load_taxonomy(taxonomy_path())


def find_field(field_id: str | None) -> TaxonomyField | None:
    if not field_id:
        return None
    return next((f for f in taxonomy().fields if f.id == field_id), None)


def find_role(field_id: str, role_id: str) -> TaxonomyRole | None:
    field = find_field(field_id)
    if field is None:
        return None
    return next((r for r in field.roles if r.id == role_id), None)


def roles_by_name() -> dict[str, tuple[TaxonomyField, TaxonomyRole]]:
    """Every role keyed by its normalised name, longest name first.

    The order matters to callers that match resume titles: "senior technical program manager"
    contains both "technical program manager" and "program manager", and the longer, more
    specific name is the right answer.
    """
    pairs = [
        (normalise(role.name), (field, role)) for field in taxonomy().fields for role in field.roles
    ]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return dict(pairs)


def normalise(text: str) -> str:
    """Lower-cased, punctuation-free, single-spaced: the form both sides of a match use."""
    return _PUNCT.sub(" ", text.lower()).strip()


def validate_track_taxonomy(track: Track) -> None:
    """Every write path for a Track goes through here so `field`/`role` never drift from the
    taxonomy they claim to come from.

    Rules: neither set is fine (a hand-written track); `field` alone must be a real field id;
    `role` always requires `field` and the two must resolve together (a role id that exists
    under a *different* field is still rejected -- it is not "this track's" role).
    """
    if track.role is not None:
        if track.field is None or find_role(track.field, track.role) is None:
            raise ProfileError(
                f"track {track.id}: role {track.role!r} does not belong to "
                f"field {track.field!r} in the taxonomy"
            )
    elif track.field is not None and find_field(track.field) is None:
        raise ProfileError(f"track {track.id}: unknown taxonomy field {track.field!r}")
