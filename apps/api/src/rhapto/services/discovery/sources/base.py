from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

from rhapto.engine.select import keyword_matches
from rhapto.services.discovery.errors import SourceError
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

__all__ = [
    "AggregatorSource",
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
    #: True when the source cannot be called without user-supplied credentials.
    needs_key: bool = False
    #: The credential field names this source needs, in the order the Settings UI shows them.
    fields: tuple[str, ...] = ()


class Source(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]: ...


class AggregatorSource(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]: ...


def matches_keywords(keywords: list[str] | tuple[str, ...], *texts: str | None) -> bool:
    if not keywords:
        return True
    return any(keyword_matches(k, t) for k in keywords for t in texts if t)


def require_credentials(info: SourceInfo, credentials: dict[str, str]) -> dict[str, str]:
    """Every field the source declares, or a SourceError naming the label and the missing one."""
    missing = [f for f in info.fields if not (credentials.get(f) or "").strip()]
    if missing:
        raise SourceError(f"{info.label}: check the API key ({', '.join(missing)} missing)")
    return {f: credentials[f].strip() for f in info.fields}
