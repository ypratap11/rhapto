from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
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
    assert body["per_source"]["api-alpha"] == {
        "found": 2,
        "new": 2,
        "error": None,
        "state": "ok",
        "failed_boards": [],
        "quota": None,
    }
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


# --- T6: per_source states, quota guard, unavailable source ------------------------------------
JS_KEY = "rk-api-test-key-456"


def _jsearch_body() -> dict[str, Any]:
    import json
    from pathlib import Path

    path = Path(__file__).parent.parent / "fixtures" / "jsearch_v2_response.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


async def _enable_jsearch(client: httpx.AsyncClient) -> None:
    put = await client.put(
        "/api/v1/settings/sources/jsearch",
        json={"enabled": True, "credentials": {"rapidapi_key": JS_KEY}},
    )
    assert put.status_code == 200, put.text


async def test_per_source_carries_state_failed_boards_quota(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from datetime import datetime

    from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse

    await _enable_jsearch(client)
    headers = {
        "x-ratelimit-requests-remaining": "187",
        "x-ratelimit-requests-limit": "200",
        "x-ratelimit-requests-reset": "3600",
    }
    fake = FakeDiscoveryHttp(
        {"jsearch.p.rapidapi.com": FakeResponse(status=200, body=_jsearch_body(), headers=headers)}
    )
    app.state.rhapto.discovery_http = fake
    body = (
        await client.post(
            "/api/v1/search", json={"query": "program manager", "sources": ["jsearch"]}
        )
    ).json()
    row = body["per_source"]["jsearch"]
    assert row["state"] == "ok" and row["failed_boards"] == [] and row["error"] is None
    assert row["quota"]["limit"] == 200 and row["quota"]["remaining"] == 187
    reset = datetime.fromisoformat(row["quota"]["reset_at"])
    assert reset.utcoffset() is not None and reset.utcoffset().total_seconds() == 0
    assert JS_KEY not in str(body)


async def test_failed_source_still_has_error_for_old_clients(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-keyed")
    ApiKeyed.result = SourceError("Api Keyed: check the API key")
    row = (await client.post("/api/v1/search", json={"query": "pm"})).json()["per_source"][
        "api-keyed"
    ]
    assert row["state"] == "failed"
    assert row["error"] == "Api Keyed: check the API key"
    assert row["failed_boards"] == [
        {"name": "api-keyed", "kind": "failed", "message": "Api Keyed: check the API key"}
    ]


async def test_themuse_enabled_row_reports_unavailable_and_makes_no_call(
    client: httpx.AsyncClient,
    app: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: Any,
) -> None:
    from rhapto.services.discovery.http import FakeDiscoveryHttp

    await _enable(session_factory, user_id, "themuse")
    fake = FakeDiscoveryHttp({})
    app.state.rhapto.discovery_http = fake
    row = (await client.post("/api/v1/search", json={"query": "pm"})).json()["per_source"][
        "themuse"
    ]
    assert row["state"] == "unavailable"
    assert row["error"] == "blocked by the vendor (bot protection), not available right now"
    assert fake.calls == []


async def test_jsearch_exhausted_search_makes_no_http_call(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    """[BR] Condition-7 witness: the quota store is assigned after app creation, so this also
    runs against code that has no guard -- where the JSearch request is made."""
    from datetime import UTC, datetime, timedelta

    from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
    from rhapto.services.discovery.quota import InMemoryQuotaStore, QuotaState

    await _enable_jsearch(client)
    store = InMemoryQuotaStore()
    reset = datetime.now(UTC) + timedelta(hours=2)
    await store.put("jsearch", JS_KEY, QuotaState(200, 0, reset))
    app.state.rhapto.quota_store = store
    fake = FakeDiscoveryHttp(
        {"jsearch.p.rapidapi.com": FakeResponse(status=200, body=_jsearch_body())}
    )
    app.state.rhapto.discovery_http = fake
    body = (
        await client.post(
            "/api/v1/search", json={"query": "program manager", "sources": ["jsearch"]}
        )
    ).json()
    assert fake.calls == []
    row = body["per_source"]["jsearch"]
    assert row["state"] == "quota_exhausted"
    assert row["error"].startswith("quota used up until ")
    assert row["quota"]["remaining"] == 0


async def test_jsearch_second_search_after_429_makes_no_call(
    client: httpx.AsyncClient, app: FastAPI
) -> None:
    from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
    from rhapto.services.discovery.quota import InMemoryQuotaStore

    await _enable_jsearch(client)
    app.state.rhapto.quota_store = InMemoryQuotaStore()
    fake = FakeDiscoveryHttp(
        {
            "jsearch.p.rapidapi.com": FakeResponse(
                status=429, headers={"x-ratelimit-requests-reset": "3600"}
            )
        }
    )
    app.state.rhapto.discovery_http = fake
    payload = {"query": "program manager", "sources": ["jsearch"]}
    first = (await client.post("/api/v1/search", json=payload)).json()["per_source"]["jsearch"]
    assert first["state"] == "quota_exhausted" and len(fake.calls) == 1
    second = (await client.post("/api/v1/search", json=payload)).json()["per_source"]["jsearch"]
    assert second["state"] == "quota_exhausted" and len(fake.calls) == 1


async def test_router_passes_the_live_only_budget(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rhapto.api.routers import search as search_router

    await _enable(session_factory, user_id, "api-alpha")
    ApiAlpha.result = [_posting(1)]
    real = search_router.live_search
    seen: dict[str, Any] = {}

    async def spy(*a: Any, **kw: Any) -> Any:
        seen.update(kw)
        return await real(*a, **kw)

    monkeypatch.setattr(search_router, "live_search", spy)
    response = await client.post("/api/v1/search", json={"query": "program manager"})
    assert response.status_code == 200
    assert seen["live_only_timeout"] == 20.0
