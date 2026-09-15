from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.live import LIVE_CAP, LiveTarget, live_search
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo

SPEC = SearchSpec(keywords=("program manager",))


def _posting(n: int, **kwargs: object) -> Posting:
    data = {
        "external_id": f"e{n}",
        "company": "ExampleCo",
        "title": f"Program Manager {n}",
        "location": "Denver, CO",
        "url": f"https://example.com/{n}",
        "jd_text": f"Program {n}. " * 20,
    }
    data.update(kwargs)
    return Posting(**data)  # type: ignore[arg-type]


class Alpha:
    info = SourceInfo("live-alpha", "aggregator", "Alpha", False)
    result: object = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        value = type(self).result
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class Beta(Alpha):
    info = SourceInfo("live-beta", "aggregator", "Beta", False)
    result: object = []


@pytest.fixture(autouse=True)
def live_sources():  # type: ignore[no-untyped-def]
    SOURCES["live-alpha"] = Alpha  # type: ignore[assignment]
    SOURCES["live-beta"] = Beta  # type: ignore[assignment]
    yield
    SOURCES.pop("live-alpha", None)
    SOURCES.pop("live-beta", None)
    Alpha.result = []
    Beta.result = []


TARGETS = [LiveTarget(source="live-alpha"), LiveTarget(source="live-beta")]


async def test_new_postings_are_stored_unscored_with_no_search_id(
    session: AsyncSession, user: User
) -> None:
    Alpha.result = [_posting(1, salary_text="$150k")]
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert {j.external_id for j in result.jobs} == {"e1", "e2"}
    assert all(j.search_id is None and j.best_fit is None for j in result.jobs)
    assert {j.salary_text for j in result.jobs} == {"$150k", None}
    assert result.per_source["live-alpha"].found == 1 and result.per_source["live-alpha"].new == 1
    assert result.per_source["live-beta"].found == 1 and result.per_source["live-beta"].new == 1
    assert len(result.new_job_ids) == 2


async def test_an_identity_match_returns_the_existing_scored_job(
    session: AsyncSession, user: User
) -> None:
    existing = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="old",
        company="ExampleCo",
        title="Program Manager 1",
        location="Denver, CO",
        url="https://gh.example/old",
        jd_text="different text " * 20,
        posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    existing.best_fit = 82
    await session.flush()
    Alpha.result = [_posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    # Opposite of the poller: a live search shows the job the user already has (with its score)
    # rather than inserting a repost row the moment they type a query.
    assert [j.id for j in result.jobs] == [existing.id]
    assert result.jobs[0].best_fit == 82
    assert result.new_job_ids == []
    assert result.per_source["live-alpha"].new == 0


async def test_a_timeout_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    async def never() -> list[Posting]:
        await asyncio.sleep(30)
        return []

    Alpha.result = never
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS, timeout=0.05
    )
    assert result.per_source["live-alpha"].error is not None
    assert "timed out" in result.per_source["live-alpha"].error
    assert result.per_source["live-beta"].new == 1
    assert [j.external_id for j in result.jobs] == ["e2"]


async def test_a_source_error_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    Alpha.result = SourceError("Alpha: check the API key")
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert result.per_source["live-alpha"].error == "Alpha: check the API key"
    assert len(result.jobs) == 1


async def test_each_source_is_capped(session: AsyncSession, user: User) -> None:
    Alpha.result = [_posting(n) for n in range(LIVE_CAP + 20)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert len(result.jobs) == LIVE_CAP
    assert result.per_source["live-alpha"].found == LIVE_CAP


async def test_posted_within_drops_old_postings_but_keeps_undated_ones(
    session: AsyncSession, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    old = _posting(1, posted_at=datetime.now(UTC) - timedelta(days=40))
    fresh = _posting(2, posted_at=datetime.now(UTC))
    undated = _posting(3)
    Alpha.result = [old, fresh, undated]
    spec = SearchSpec(keywords=("program manager",), posted_within="30d")
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=spec, targets=[TARGETS[0]]
    )
    assert {j.external_id for j in result.jobs} == {"e2", "e3"}


async def test_results_are_ordered_scored_first(session: AsyncSession, user: User) -> None:
    scored = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="old",
        company="ExampleCo",
        title="Program Manager 1",
        location="Denver, CO",
        url="https://gh.example/old",
        jd_text="different " * 20,
        posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    scored.best_fit = 70
    await session.flush()
    Alpha.result = [_posting(2), _posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert result.jobs[0].id == scored.id
    assert result.jobs[1].best_fit is None
