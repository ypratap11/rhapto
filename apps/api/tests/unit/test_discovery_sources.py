"""Every registered source passes the same contract against its recorded (fictional) fixture."""

import json
import re
from pathlib import Path

import pytest

from rhapto.models.profile.watchlist import AggregatorEntry, WatchlistEntry
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.sources import (
    SOURCES,
    aggregator_sources,
    all_sources,
    board_sources,
    get_source,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "discovery"
#: Sources whose board string is not a bare slug (Workday needs a host prefix and a site).
BOARDS = {"workday": "exampleco.wd5/ExampleCoCareers"}


def fake_http_for(name: str) -> FakeDiscoveryHttp:
    routes = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return FakeDiscoveryHttp(routes)


#: SearchSpec-driven aggregators (themuse, remotive, adzuna, jooble, jsearch) only implement
#: `fetch_search`; their contract is covered by test_discovery_search_sources.py instead.
FETCH_SOURCES = sorted(name for name, cls in SOURCES.items() if hasattr(cls, "fetch"))


@pytest.mark.parametrize("name", FETCH_SOURCES)
async def test_source_contract(name: str) -> None:
    source = get_source(name)
    board = BOARDS.get(name, "exampleco") if source.info.needs_board else None
    postings = await source.fetch(fake_http_for(name), board=board, keywords=[])
    assert postings, f"{name} fixture produced no postings"
    for p in postings:
        assert p.external_id and p.title and p.company and p.jd_text
        assert p.url.startswith("https://")
        assert not re.search(r"<[a-z][^>]*>", p.jd_text), f"{name}: HTML leaked into jd_text"
        assert p.posted_at is None or p.posted_at.tzinfo is not None


def test_registry_matches_profile_schema_enums() -> None:
    board_enum = set(WatchlistEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    aggregator_enum = set(AggregatorEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    assert {i.name for i in board_sources()} <= board_enum
    # The profile watchlist schema only lists the key-free legacy aggregators (remoteok,
    # hn-hiring); SearchSpec-driven aggregators (themuse, remotive, adzuna, jooble, jsearch)
    # are driven by saved searches, not watchlist.yaml, so the registry is a superset here.
    assert aggregator_enum <= {i.name for i in aggregator_sources()}
    assert {i.name for i in all_sources()} == set(SOURCES)
