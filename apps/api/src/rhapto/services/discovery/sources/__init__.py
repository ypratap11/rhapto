from __future__ import annotations

from rhapto.services.discovery.sources.base import Source, SourceError, SourceInfo

SOURCES: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    SOURCES[cls.info.name] = cls
    return cls


def get_source(name: str) -> Source:
    try:
        return SOURCES[name]()
    except KeyError as exc:
        raise SourceError(f"unknown source {name!r}") from exc


def all_sources() -> list[SourceInfo]:
    return [cls.info for cls in SOURCES.values()]


def board_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "board"]


def aggregator_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "aggregator"]


from rhapto.services.discovery.sources import (  # noqa: E402,F401,I001  (registration)
    ashby,
    greenhouse,
    hn_hiring,
    lever,
    remoteok,
    workday,
)
