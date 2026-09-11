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


def fake_http_for(name: str) -> FakeDiscoveryHttp:
    routes = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return FakeDiscoveryHttp(routes)


@pytest.mark.parametrize("name", sorted(SOURCES))
async def test_source_contract(name: str) -> None:
    source = get_source(name)
    board = "exampleco" if source.info.needs_board else None
    postings = await source.fetch(fake_http_for(name), board=board, keywords=[])
    assert postings, f"{name} fixture produced no postings"
    for p in postings:
        assert p.external_id and p.title and p.company and p.jd_text
        assert p.url.startswith("https://")
        assert not re.search(r"<[a-z][^>]*>", p.jd_text), f"{name}: HTML leaked into jd_text"
        assert p.posted_at is None or p.posted_at.tzinfo is not None


@pytest.mark.xfail(strict=True, reason="adapters land in Tasks 5 and 6")
def test_registry_matches_profile_schema_enums() -> None:
    board_enum = set(WatchlistEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    aggregator_enum = set(AggregatorEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    assert {i.name for i in board_sources()} <= board_enum
    assert {i.name for i in aggregator_sources()} == aggregator_enum
    assert {i.name for i in all_sources()} == set(SOURCES)
