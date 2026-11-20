"""JSearch /search-v2 adapter: one request, new response shape, quota headers (FakeDiscoveryHttp only)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import get_aggregator
from rhapto.services.discovery.sources.base import SourceError

FIXTURE = Path(__file__).parent.parent / "fixtures" / "jsearch_v2_response.json"
CREDS = {"rapidapi_key": "rk-test-key-123"}


def _body() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


async def test_jsearch_v2_maps_fixture() -> None:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com/search-v2": _body()})
    spec = SearchSpec(keywords=("program manager",), location="Denver, CO")
    postings = await get_aggregator("jsearch").fetch_search(http, spec, CREDS)  # type: ignore[arg-type]
    by_id = {p.external_id: p for p in postings}
    assert set(by_id) == {"jid-1", "jid-2"}  # the barista row fails the keyword filter
    first = by_id["jid-1"]
    assert first.company == "ExampleCo 1"
    assert first.title == "Technical Program Manager"
    assert first.location == "Denver, CO, US"
    assert first.url == "https://example.com/apply/1"
    assert first.salary_text == "150000-170000"
    assert first.posted_at == datetime(2026, 11, 10, 8, 30, tzinfo=UTC)
    assert "programs" in first.jd_text and "<p>" not in first.jd_text
    assert by_id["jid-2"].salary_text is None


async def test_jsearch_remote_only_filters_locally() -> None:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com/search-v2": _body()})
    spec = SearchSpec(keywords=("program manager",), remote="only")
    postings = await get_aggregator("jsearch").fetch_search(http, spec, CREDS)  # type: ignore[arg-type]
    assert [p.external_id for p in postings] == ["jid-2"]
    assert "remote_jobs_only" not in http.calls[0]


async def test_jsearch_makes_exactly_one_request_for_many_keywords() -> None:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com/search-v2": _body()})
    spec = SearchSpec(keywords=("a", "b", "c", "d", "program manager"), location="Denver, CO")
    await get_aggregator("jsearch").fetch_search(http, spec, CREDS)  # type: ignore[arg-type]
    assert len(http.calls) == 1
    url = http.calls[0]
    assert "/search-v2?query=" in url and "country=us" in url
    for banned in ("page=", "num_pages", "cursor", "remote_jobs_only"):
        assert banned not in url
    assert "rk-test-key-123" not in url
    assert http.headers[0]["x-rapidapi-key"] == "rk-test-key-123"
    assert http.headers[0]["x-rapidapi-host"] == "jsearch.p.rapidapi.com"


@pytest.mark.parametrize("bad", [[], {"data": []}, {"data": {"jobs": "x"}}, {"data": None}, "oops"])
async def test_jsearch_unexpected_shape_raises_source_error(bad: Any) -> None:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": bad})
    with pytest.raises(SourceError, match="unexpected response shape"):
        await get_aggregator("jsearch").fetch_search(http, SearchSpec(keywords=("pm",)), CREDS)  # type: ignore[arg-type]


async def test_jsearch_parses_quota_headers() -> None:
    headers = {
        "x-ratelimit-requests-remaining": "187",
        "x-ratelimit-requests-limit": "200",
        "x-ratelimit-requests-reset": "3600",
    }
    http = FakeDiscoveryHttp(
        {"jsearch.p.rapidapi.com": FakeResponse(status=200, body=_body(), headers=headers)}
    )
    adapter: Any = get_aggregator("jsearch")
    await adapter.fetch_search(http, SearchSpec(keywords=("program manager",)), CREDS)
    quota = adapter.quota
    assert (quota.remaining, quota.limit, quota.reset_seconds) == (187, 200, 3600)


async def test_jsearch_without_a_key_raises_before_any_call() -> None:
    http = FakeDiscoveryHttp({})
    with pytest.raises(SourceError):
        await get_aggregator("jsearch").fetch_search(http, SearchSpec(keywords=("pm",)), {})  # type: ignore[arg-type]
    assert http.calls == []


def _body_with(*jobs: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"jobs": list(jobs)}}


def _job(jid: str, title: str, description: str, **extra: Any) -> dict[str, Any]:
    return {
        "job_id": jid,
        "job_title": title,
        "job_description": description,
        "job_apply_link": f"https://example.com/apply/{jid}",
        "employer_name": "ExampleCo",
        **extra,
    }


async def _kept(query: str, *jobs: dict[str, Any]) -> set[str]:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com/search-v2": _body_with(*jobs)})
    postings = await get_aggregator("jsearch").fetch_search(
        http,  # type: ignore[arg-type]
        SearchSpec(keywords=(query,)),
        CREDS,
    )
    return {p.external_id for p in postings}


async def test_multiword_query_matches_words_in_any_order() -> None:
    job = _job("a", "Director, Enterprise Applications", "Lead AI adoption.")
    assert await _kept("director AI enterprise applications", job) == {"a"}


async def test_ai_director_matches_director_of_ai() -> None:
    assert await _kept("AI director", _job("a", "Director of AI", "Run the team.")) == {"a"}


async def test_city_typed_in_the_query_matches_the_posting_city() -> None:
    job = _job("a", "Director of AI", "Run the team.", job_city="Austin")
    assert await _kept("AI director Austin", job) == {"a"}


async def test_posting_missing_a_significant_word_is_dropped() -> None:
    job = _job("a", "Director, Enterprise Applications", "Lead cloud work.")
    assert await _kept("director AI enterprise applications", job) == set()


async def test_it_is_not_a_stop_word() -> None:
    ops = _job("a", "Operations Manager", "Run the floor.")
    it = _job("b", "IT Manager", "Run the floor.")
    assert await _kept("IT manager", ops, it) == {"b"}


async def test_stop_word_only_query_falls_back_to_exact_phrase() -> None:
    barista = _job("a", "Barista", "Make coffee.")
    phrase = _job("b", "Clerk", "Sort the and tags.")
    assert await _kept("the and", barista, phrase) == {"b"}


async def test_symbol_queries_keep_working() -> None:
    cpp = _job("a", "C++ Engineer", "Build things.")
    barista = _job("b", "Barista", "Make coffee.")
    net = _job("c", ".NET Developer", "Build things.")
    assert await _kept("C++", cpp, barista) == {"a"}
    assert await _kept(".NET", net, barista) == {"c"}
