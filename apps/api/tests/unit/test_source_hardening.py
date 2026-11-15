"""Hostile quota headers never fail a search; vendor keys never reach httpx request logs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
import pytest

from rhapto.services.discovery.errors import Quota, RateLimited
from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
from rhapto.services.discovery.quota import InMemoryQuotaStore, guarded_search
from rhapto.services.discovery.search import SearchSpec

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
SPEC = SearchSpec(keywords=("program manager",))
CREDS = {"rapidapi_key": "rk-test"}
JOBS = {
    "status": "OK",
    "data": {
        "jobs": [
            {
                "job_id": "j1",
                "job_title": "Program Manager",
                "employer_name": "ExampleCo",
                "job_apply_link": "https://example.com/a",
                "job_description": "Run programs.",
            }
        ],
        "cursor": "c",
    },
}
HOSTILE = ["99999999999999", "-5", "-99999999999999", "nan", "1e400", "inf", "3.5"]


def _clock() -> datetime:
    return NOW


@pytest.mark.parametrize("reset", HOSTILE)
async def test_hostile_reset_header_keeps_postings(reset: str) -> None:
    headers = {
        "x-ratelimit-requests-remaining": "5",
        "x-ratelimit-requests-limit": "200",
        "x-ratelimit-requests-reset": reset,
    }
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": FakeResponse(body=JOBS, headers=headers)})
    result = await guarded_search(
        InMemoryQuotaStore(now=_clock),
        "jsearch",
        http,
        SPEC,
        CREDS,
        now=_clock,  # type: ignore[arg-type]
    )
    assert len(result.postings) == 1


@pytest.mark.parametrize("reset", [10**14, -5, -(10**14), 0])
async def test_hostile_reset_on_429_does_not_raise(reset: int) -> None:
    exc = RateLimited("429", quota=Quota(limit=None, remaining=None, reset_seconds=reset))
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": exc})
    result = await guarded_search(
        InMemoryQuotaStore(now=_clock),
        "jsearch",
        http,
        SPEC,
        CREDS,
        now=_clock,  # type: ignore[arg-type]
    )
    assert result.rate_limited is True


async def test_httpx_request_log_does_not_contain_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    key = "JOOBLE-KEY-d41d8cd9-distinct"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await client.post(f"https://jooble.org/api/{key}", json={"keywords": "x"})
    assert key not in caplog.text
