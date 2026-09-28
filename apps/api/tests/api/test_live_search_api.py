from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Aggregator
from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistModel
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo


class ApiAlpha:
    info = SourceInfo("api-alpha", "aggregator", "Api Alpha", False)
    result: object = []
    seen: list[SearchSpec] = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        type(self).seen.append(spec)
        value = type(self).result
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class ApiKeyed(ApiAlpha):
    info = SourceInfo(
        "api-keyed", "aggregator", "Api Keyed", False, needs_key=True, fields=("api_key",)
    )
    result: object = []
    seen: list[SearchSpec] = []


@pytest.fixture(autouse=True)
def api_sources():  # type: ignore[no-untyped-def]
    ApiAlpha.result, ApiAlpha.seen = [], []
    ApiKeyed.result, ApiKeyed.seen = [], []
    SOURCES["api-alpha"] = ApiAlpha  # type: ignore[assignment]
    SOURCES["api-keyed"] = ApiKeyed  # type: ignore[assignment]
    yield
    SOURCES.pop("api-alpha", None)
    SOURCES.pop("api-keyed", None)


def _posting(n: int) -> Posting:
    return Posting(
        external_id=f"e{n}",
        company="ExampleCo",
        title=f"Program Manager {n}",
        location="Denver, CO",
        url=f"https://example.com/{n}",
        jd_text=f"Program {n}. " * 20,
        salary_text="$150k" if n == 1 else None,
    )


async def _enable(
    session_factory: async_sessionmaker[AsyncSession], user_id: Any, *sources: str
) -> None:
    """Make this account's enabled aggregators EXACTLY `sources`, and nothing else.

    Existing rows are cleared first, which matters for two reasons. `ensure_account` seeds an enabled
    row for every keyless source at account creation -- and these test doubles register themselves as
    keyless aggregators, so the seed includes them and a blind insert hits
    `aggregators_user_id_source_key`. More importantly, a test about which sources a live search fans
    out to should say which sources are enabled rather than inherit whatever the seed happened to
    create.

    The pydantic AggregatorEntry model restricts `source` to the real, registered aggregator ids (see
    test_poller.py), so these throwaway test ids are inserted straight through the ORM row instead of
    profile_repo.replace_aggregators.
    """
    async with session_factory() as session:
        await session.execute(delete(Aggregator).where(Aggregator.user_id == user_id))
        for source in sources:
            session.add(Aggregator(user_id=user_id, source=source, enabled=True, keywords=[]))
        await session.commit()


async def test_a_search_returns_jobs_and_per_source_counts(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha")
    ApiAlpha.result = [_posting(1), _posting(2)]
    response = await client.post(
        "/api/v1/search",
        json={"query": "program manager", "location": "Denver, CO", "remote": "include"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["jobs"]) == 2
    assert body["per_source"]["api-alpha"] == {"found": 2, "new": 2, "error": None}
    assert {j["salary_text"] for j in body["jobs"]} == {"$150k", None}
    # New jobs come back unscored; the client refetches GET /jobs?ids= until they have a ring.
    assert all(j["best_fit"] is None for j in body["jobs"])
    ids = ",".join(j["id"] for j in body["jobs"])
    assert len((await client.get(f"/api/v1/jobs?ids={ids}")).json()) == 2
    assert ApiAlpha.seen[0].keywords == ("program manager",)
    assert ApiAlpha.seen[0].location == "Denver, CO"


async def test_a_failing_source_is_reported_and_the_rest_still_answer(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha", "api-keyed")
    ApiAlpha.result = [_posting(1)]
    ApiKeyed.result = SourceError("Api Keyed: check the API key")
    body = (await client.post("/api/v1/search", json={"query": "program manager"})).json()
    assert body["per_source"]["api-keyed"]["error"] == "Api Keyed: check the API key"
    assert body["per_source"]["api-alpha"]["new"] == 1
    assert len(body["jobs"]) == 1


async def test_a_slow_source_times_out_without_failing_the_request(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rhapto.api.routers import search as search_router

    monkeypatch.setattr(search_router, "LIVE_TIMEOUT_SECONDS", 0.05)
    await _enable(session_factory, user_id, "api-alpha")

    async def never() -> list[Posting]:
        await asyncio.sleep(30)
        return []

    ApiAlpha.result = never
    response = await client.post("/api/v1/search", json={"query": "program manager"})
    assert response.status_code == 200
    assert "timed out" in response.json()["per_source"]["api-alpha"]["error"]


async def test_watchlist_boards_are_searched_too(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    async with session_factory() as session:
        await profile_repo.replace_watchlist(
            session,
            user_id,
            [
                WatchlistModel(
                    company="ExampleCo", source="greenhouse", board="exampleco", keywords=[]
                )
            ],
        )
        await session.commit()
    body = (await client.post("/api/v1/search", json={"query": "program manager"})).json()
    # The fake HTTP client has no route for the Greenhouse board, so the board reports an error
    # instead of the request failing.
    assert "greenhouse" in body["per_source"]


async def test_the_sources_filter_narrows_the_fan_out(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha", "api-keyed")
    ApiAlpha.result = [_posting(1)]
    body = (
        await client.post(
            "/api/v1/search", json={"query": "program manager", "sources": ["api-alpha"]}
        )
    ).json()
    assert list(body["per_source"]) == ["api-alpha"]


async def test_validation(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/search", json={"query": ""})).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"query": "pm", "remote": "maybe"})
    ).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"query": "pm", "field": "not-a-field"})
    ).status_code == 422
