from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

from rhapto.engine.select import keyword_matches
from rhapto.services.discovery.errors import SourceError
from rhapto.services.discovery.posting import Posting

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

__all__ = [
    "Source",
    "SourceError",
    "SourceInfo",
    "matches_keywords",
]


@dataclass(frozen=True)
class SourceInfo:
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool


class Source(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]: ...


def matches_keywords(keywords: list[str], *texts: str | None) -> bool:
    if not keywords:
        return True
    return any(keyword_matches(k, t) for k in keywords for t in texts if t)
