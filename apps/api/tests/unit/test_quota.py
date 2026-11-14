"""Quota store and guard. Fakes only: no real Redis, no real vendor."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
from rhapto.services.discovery.search import SearchSpec

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
KEY = "rk-secret-key-abc123"
SPEC = SearchSpec(keywords=("program manager",))
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
OK_HEADERS = {
    "x-ratelimit-requests-remaining": "187",
    "x-ratelimit-requests-limit": "200",
    "x-ratelimit-requests-reset": "3600",
}
CREDS = {"rapidapi_key": KEY}


def _clock() -> datetime:
    return NOW


class StubRedis:
    """Dict-backed stand-in for redis.asyncio.Redis (get / set with ex)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex


class BrokenRedis:
    async def get(self, key: str) -> str | None:
        raise ConnectionError(f"down while reading {key}")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise ConnectionError(f"down while writing {key}")


class RaisingStore:
    async def get(self, source: str, api_key: str) -> Any:
        raise RuntimeError("store down")

    async def put(self, source: str, api_key: str, state: Any) -> None:
        raise RuntimeError("store down")


def _http(route: Any) -> FakeDiscoveryHttp:
    return FakeDiscoveryHttp({"jsearch.p.rapidapi.com": route})


async def test_quota_store_keys_by_fingerprint_not_key() -> None:
    from rhapto.services.discovery.quota import (
        InMemoryQuotaStore,
        QuotaState,
        RedisQuotaStore,
        key_fingerprint,
    )

    state = QuotaState(limit=200, remaining=5, reset_at=NOW + timedelta(hours=1))
    stub = StubRedis()
    redis_store = RedisQuotaStore("redis://unused", client=stub, now=_clock)
    await redis_store.put("jsearch", KEY, state)
    assert list(stub.data) == [f"rhapto:quota:jsearch:{key_fingerprint(KEY)}"]
    assert len(key_fingerprint(KEY)) == 16
    int(key_fingerprint(KEY), 16)  # 16 hex characters
    assert KEY not in "".join(stub.data) and KEY not in "".join(stub.data.values())
    assert 3600 < next(iter(stub.ttls.values())) <= 3660
    assert await redis_store.get("jsearch", KEY) == state

    mem = InMemoryQuotaStore(now=_clock)
    await mem.put("jsearch", KEY, state)
    assert KEY not in repr(mem.__dict__)
    assert await mem.get("jsearch", KEY) == state


async def test_same_key_shares_state_different_key_does_not() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, QuotaState

    store = InMemoryQuotaStore(now=_clock)
    state = QuotaState(200, 0, NOW + timedelta(hours=1))
    await store.put("jsearch", KEY, state)
    assert await store.get("jsearch", KEY) == state
    assert await store.get("jsearch", "another-key") is None


async def test_in_memory_store_honours_expiry() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, QuotaState

    clock = [NOW]
    store = InMemoryQuotaStore(now=lambda: clock[0])
    await store.put("jsearch", KEY, QuotaState(200, 0, NOW + timedelta(seconds=30)))
    assert await store.get("jsearch", KEY) is not None
    clock[0] = NOW + timedelta(hours=1)
    assert await store.get("jsearch", KEY) is None


async def test_redis_store_fails_open_and_does_not_log_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from rhapto.services.discovery.quota import QuotaState, RedisQuotaStore

    store = RedisQuotaStore("redis://unused", client=BrokenRedis(), now=_clock)
    with caplog.at_level(logging.DEBUG):
        assert await store.get("jsearch", KEY) is None
        await store.put("jsearch", KEY, QuotaState(200, 0, NOW + timedelta(hours=1)))
    assert KEY not in caplog.text
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_quota_state_from_and_exhausted() -> None:
    from rhapto.services.discovery.errors import Quota
    from rhapto.services.discovery.quota import QuotaState, exhausted, quota_state_from

    assert quota_state_from(None, NOW) is None
    state = quota_state_from(Quota(limit=200, remaining=0, reset_seconds=120), NOW)
    assert state == QuotaState(200, 0, NOW + timedelta(seconds=120))
    assert exhausted(state, NOW) is True
    assert exhausted(state, NOW + timedelta(seconds=121)) is False
    assert exhausted(QuotaState(200, 5, NOW + timedelta(hours=1)), NOW) is False
    assert exhausted(QuotaState(200, 0, None), NOW) is False
    assert exhausted(None, NOW) is False


async def test_guard_makes_no_call_at_zero_remaining() -> None:
    from rhapto.services.discovery.errors import SourceError
    from rhapto.services.discovery.quota import (
        InMemoryQuotaStore,
        QuotaState,
        describe,
        guarded_search,
    )

    store = InMemoryQuotaStore(now=_clock)
    reset = NOW + timedelta(hours=2)
    await store.put("jsearch", KEY, QuotaState(200, 0, reset))
    http = _http(SourceError("must not be called"))
    result = await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert http.calls == []
    assert result.skipped is True and result.rate_limited is False and result.postings == []
    assert describe(result.state) == f"quota used up until {reset.isoformat()}"


async def test_guard_calls_again_after_reset_time_passes() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, QuotaState, guarded_search

    store = InMemoryQuotaStore()  # real clock: the stored reset is already in the past
    past = datetime.now(UTC) - timedelta(seconds=5)
    await store.put("jsearch", KEY, QuotaState(200, 0, past))
    http = _http(FakeResponse(200, JOBS, OK_HEADERS))
    result = await guarded_search(store, "jsearch", http, SPEC, CREDS)  # type: ignore[arg-type]
    assert len(http.calls) == 1 and result.skipped is False
    assert [p.external_id for p in result.postings] == ["j1"]


async def test_guard_stores_the_quota_from_a_successful_search() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, guarded_search

    store = InMemoryQuotaStore(now=_clock)
    http = _http(FakeResponse(200, JOBS, OK_HEADERS))
    result = await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert result.state is not None and result.state.remaining == 187 and result.state.limit == 200
    assert result.state.reset_at == NOW + timedelta(seconds=3600)
    assert await store.get("jsearch", KEY) == result.state


async def test_429_returns_guarded_state_not_exception() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, describe, guarded_search

    store = InMemoryQuotaStore(now=_clock)
    http = _http(FakeResponse(429, None, {"x-ratelimit-requests-reset": "600"}))
    result = await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert result.rate_limited is True and result.skipped is False and result.postings == []
    reset = NOW + timedelta(seconds=600)
    assert describe(result.state) == f"quota used up until {reset.isoformat()}"
    assert KEY not in describe(result.state)


async def test_429_with_reset_header_stores_zero_and_next_search_makes_no_call() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, guarded_search

    store = InMemoryQuotaStore(now=_clock)
    http = _http(FakeResponse(429, None, {"x-ratelimit-requests-reset": "600"}))
    await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    stored = await store.get("jsearch", KEY)
    assert stored is not None and stored.remaining == 0
    assert stored.reset_at == NOW + timedelta(seconds=600)
    again = await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert again.skipped is True
    assert len(http.calls) == 1  # only the first search reached the vendor


async def test_429_without_reset_header_stores_one_hour_and_uses_generic_wording() -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore, describe, guarded_search

    store = InMemoryQuotaStore(now=_clock)
    http = _http(FakeResponse(429, None, {}))
    result = await guarded_search(store, "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert result.rate_limited is True
    assert describe(result.state) == "rate-limited (quota used up, try again later)"
    stored = await store.get("jsearch", KEY)
    assert stored is not None and stored.remaining == 0
    assert stored.reset_at == NOW + timedelta(hours=1)


async def test_redis_failure_fails_open() -> None:
    from rhapto.services.discovery.quota import guarded_search

    http = _http(FakeResponse(200, JOBS, OK_HEADERS))
    result = await guarded_search(RaisingStore(), "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert [p.external_id for p in result.postings] == ["j1"]
    assert len(http.calls) == 1


async def test_vendor_429_is_the_backstop_when_the_store_is_down() -> None:
    from rhapto.services.discovery.quota import guarded_search

    http = _http(FakeResponse(429, None, {"x-ratelimit-requests-reset": "60"}))
    result = await guarded_search(RaisingStore(), "jsearch", http, SPEC, CREDS, now=_clock)  # type: ignore[arg-type]
    assert result.rate_limited is True


async def test_no_key_or_no_store_skips_the_guard() -> None:
    from rhapto.services.discovery.errors import SourceError
    from rhapto.services.discovery.quota import InMemoryQuotaStore, guarded_search

    http = _http(FakeResponse(200, JOBS, OK_HEADERS))
    with pytest.raises(SourceError):  # the adapter's own missing-credentials error
        await guarded_search(InMemoryQuotaStore(), "jsearch", http, SPEC, {})  # type: ignore[arg-type]
    result = await guarded_search(None, "jsearch", http, SPEC, CREDS)  # type: ignore[arg-type]
    assert len(result.postings) == 1


async def test_other_errors_propagate_unchanged() -> None:
    from rhapto.services.discovery.errors import SourceError
    from rhapto.services.discovery.quota import InMemoryQuotaStore, guarded_search

    http = _http(FakeResponse(500, None, {}))
    with pytest.raises(SourceError) as exc:
        await guarded_search(InMemoryQuotaStore(), "jsearch", http, SPEC, CREDS)  # type: ignore[arg-type]
    assert KEY not in str(exc.value)


def test_redis_value_holds_no_key_material() -> None:
    from rhapto.services.discovery.quota import QuotaState, encode_state

    value = encode_state(QuotaState(200, 3, NOW))
    assert set(json.loads(value)) == {"limit", "remaining", "reset_at"}
