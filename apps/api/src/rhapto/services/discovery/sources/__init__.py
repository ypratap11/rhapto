from __future__ import annotations

from typing import cast

from rhapto.services.discovery.sources.base import (
    AggregatorSource,
    Source,
    SourceError,
    SourceInfo,
)

#: Board/keyword sources implement `Source` (`.fetch`); SearchSpec-driven aggregators implement
#: `AggregatorSource` (`.fetch_search`) instead — some (hn-hiring, remoteok) implement both.
SourceClass = type[Source] | type[AggregatorSource]

SOURCES: dict[str, SourceClass] = {}


def register[T: (Source | AggregatorSource)](cls: type[T]) -> type[T]:
    SOURCES[cls.info.name] = cast("SourceClass", cls)
    return cls


def get_source(name: str) -> Source:
    try:
        return cast("Source", SOURCES[name]())
    except KeyError as exc:
        raise SourceError(f"unknown source {name!r}") from exc


def all_sources() -> list[SourceInfo]:
    return [cls.info for cls in SOURCES.values()]


def board_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "board"]


def aggregator_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "aggregator"]


def get_aggregator(name: str) -> AggregatorSource:
    """The aggregator registered under `name`; a board source is a programming error here."""
    cls = SOURCES.get(name)
    if cls is None:
        raise SourceError(f"unknown source {name!r}")
    if cls.info.kind != "aggregator":
        raise SourceError(f"{name!r} is a board source, not an aggregator")
    return cast("AggregatorSource", cls())


from rhapto.services.discovery.sources import (  # noqa: E402,F401,I001  (registration)
    ashby,
    greenhouse,
    hn_hiring,
    lever,
    remoteok,
    workday,
    themuse,
    remotive,
    adzuna,
    jooble,
    jsearch,
)
