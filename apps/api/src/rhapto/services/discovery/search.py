"""What a saved or live search asks a source for, and the rules every source shares."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Results per search per source in the background poll. The live path uses LIVE_CAP instead.
SEARCH_CAP = 100

Remote = Literal["include", "only", "exclude"]
PostedWithin = Literal["24h", "7d", "30d", "any"]

_REMOTE_WORDS = ("remote", "anywhere", "flexible", "distributed", "work from home")


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
