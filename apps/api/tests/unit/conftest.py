from __future__ import annotations

from collections.abc import Iterator

import pytest
from test_poller import FakeAggregator, KeyedAggregator

from rhapto.services.discovery.sources import SOURCES


@pytest.fixture
def fake_aggregators() -> Iterator[None]:
    """Registers `FakeAggregator`/`KeyedAggregator` (see test_poller.py) under throwaway ids so a
    poll can be driven without any HTTP at all. Shared by test_poller.py and test_unlisted.py."""
    FakeAggregator.seen = []
    FakeAggregator.postings = []
    FakeAggregator.fail_names = set()
    SOURCES["fake-agg"] = FakeAggregator  # type: ignore[assignment]
    SOURCES["fake-keyed"] = KeyedAggregator  # type: ignore[assignment]
    yield
    SOURCES.pop("fake-agg", None)
    SOURCES.pop("fake-keyed", None)
