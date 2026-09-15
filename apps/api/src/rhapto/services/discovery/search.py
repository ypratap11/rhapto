"""What a saved or live search asks a source for, and the rules every source shares."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SearchRow
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo

#: Results per search per source in the background poll. The live path uses LIVE_CAP instead.
SEARCH_CAP = 100

Remote = Literal["include", "only", "exclude"]
PostedWithin = Literal["24h", "7d", "30d", "any"]

_REMOTE_WORDS = ("remote", "anywhere", "flexible", "distributed", "work from home")
_FALSEY = frozenset({"no", "false", "0", "never"})


@dataclass(frozen=True)
class SearchSpec:
    """One search, in the shape every aggregator understands.

    `field` is a taxonomy field id (see services/taxonomy.py): The Muse and Adzuna turn it into
    their own category name; keyword-only sources ignore it. `posted_within` is applied by the
    caller (the live path) rather than by the sources, because only some APIs can express it.
    """

    keywords: tuple[str, ...]
    location: str | None = None
    remote: Remote = "include"
    name: str = ""
    field: str | None = None
    posted_within: PostedWithin = "any"


def query_text(spec: SearchSpec) -> str:
    """The keywords as one boolean phrase, for sources that accept one."""
    return " OR ".join(k.strip() for k in spec.keywords if k.strip())


def remote_matches(spec: SearchSpec, location_text: str | None, remote_flag: bool | None) -> bool:
    """Does this posting satisfy the spec's remote preference?

    `remote_flag` wins when the source states it; otherwise the location text is read for the
    usual words. `include` accepts everything, so it never inspects either.
    """
    if spec.remote == "include":
        return True
    is_remote = remote_flag
    if is_remote is None:
        text = (location_text or "").lower()
        is_remote = any(word in text for word in _REMOTE_WORDS)
    return is_remote if spec.remote == "only" else not is_remote


async def derive_searches(session: AsyncSession, user_id: uuid.UUID) -> list[SearchRow]:
    """One saved search per track, created only when the user has none at all.

    Returns the rows it created, so an empty list means "the user already has searches" and the
    caller should leave them alone.
    """
    if await searches_repo.list_searches(session, user_id):
        return []
    answers = await profile_repo.get_answers(session, user_id)
    preferred = [
        p.strip() for p in (answers.get("location_preferred") or "").split(",") if p.strip()
    ]
    # The preferred list is "Town, ST, Town, ST"; the first town and its state are the first two
    # entries, and a single entry with no state is used as-is.
    location = ", ".join(preferred[:2]) if preferred else (answers.get("location_home") or None)
    remote: Remote = (
        "exclude" if (answers.get("remote_ok") or "").strip().lower() in _FALSEY else "include"
    )
    created: list[SearchRow] = []
    for track in await profile_repo.list_tracks(session, user_id):
        created.append(
            await searches_repo.create_search(
                session,
                user_id,
                name=track.name[:100],
                keywords=list(track.keywords)[:6],
                location=location,
                remote=remote,
                derived_from_track_id=track.track_id,
            )
        )
    return created
