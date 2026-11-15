"""Vendor quota state and the guard that keeps a live-only source inside its free plan.

The RapidAPI quota belongs to the API key, so state is keyed by a fingerprint of the key
(`sha256(key)[:16]`): two accounts sharing a key share one state, and no key material is ever
stored, logged or put in an error. This module imports nothing from `rhapto.api`.

Redis down means the guard fails open (the search still runs); the vendor's own 429 is the
backstop and writes the state again.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import redis.asyncio as aioredis

from rhapto.services.discovery.errors import Quota, RateLimited
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import get_aggregator

logger = logging.getLogger(__name__)

#: Used when the vendor's 429 carries no reset header.
DEFAULT_COOLDOWN = timedelta(hours=1)
_TTL_SLACK_SECONDS = 60
GENERIC_WORDING = "rate-limited (quota used up, try again later)"

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class QuotaState:
    limit: int | None
    remaining: int | None
    reset_at: datetime | None  # UTC


class QuotaStore(Protocol):
    async def get(self, source: str, api_key: str) -> QuotaState | None: ...

    async def put(self, source: str, api_key: str, state: QuotaState) -> None: ...


def key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def _store_key(source: str, api_key: str) -> str:
    return f"rhapto:quota:{source}:{key_fingerprint(api_key)}"


def encode_state(state: QuotaState) -> str:
    return json.dumps(
        {
            "limit": state.limit,
            "remaining": state.remaining,
            "reset_at": state.reset_at.isoformat() if state.reset_at else None,
        }
    )


def _decode_state(raw: str) -> QuotaState | None:
    try:
        data = json.loads(raw)
        reset = data.get("reset_at")
        return QuotaState(
            limit=data.get("limit"),
            remaining=data.get("remaining"),
            reset_at=datetime.fromisoformat(reset) if reset else None,
        )
    except (ValueError, TypeError, AttributeError):
        return None


class InMemoryQuotaStore:
    """Test store (and a safe default for tools): honours expiry, injectable clock."""

    def __init__(self, now: Clock = _utcnow) -> None:
        self._now = now
        self._states: dict[str, QuotaState] = {}

    async def get(self, source: str, api_key: str) -> QuotaState | None:
        key = _store_key(source, api_key)
        state = self._states.get(key)
        if state is not None and state.reset_at is not None and state.reset_at <= self._now():
            del self._states[key]
            return None
        return state

    async def put(self, source: str, api_key: str, state: QuotaState) -> None:
        self._states[_store_key(source, api_key)] = state


class RedisQuotaStore:
    """Redis-backed store. Every Redis error is logged (no key material) and swallowed."""

    def __init__(self, redis_url: str, *, client: Any = None, now: Clock = _utcnow) -> None:
        self._now = now
        # Short timeouts: a dead Redis must not eat the live-search budget before failing open.
        self._redis: Any = client or aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )

    async def get(self, source: str, api_key: str) -> QuotaState | None:
        try:
            raw = await self._redis.get(_store_key(source, api_key))
        except Exception as exc:
            logger.warning(
                "quota store read failed (%s); continuing without the guard", type(exc).__name__
            )
            return None
        if raw is None:
            return None
        return _decode_state(raw if isinstance(raw, str) else raw.decode("utf-8"))

    async def put(self, source: str, api_key: str, state: QuotaState) -> None:
        if state.reset_at is None:
            ttl = int(DEFAULT_COOLDOWN.total_seconds())
        else:
            ttl = max(int((state.reset_at - self._now()).total_seconds()), 0)
        try:
            await self._redis.set(
                _store_key(source, api_key), encode_state(state), ex=ttl + _TTL_SLACK_SECONDS
            )
        except Exception as exc:
            logger.warning("quota store write failed (%s); state not saved", type(exc).__name__)

    async def close(self) -> None:
        await self._redis.aclose()


#: A vendor header is untrusted: keep any reset inside 0..one year so date maths cannot overflow.
MAX_RESET_SECONDS = 366 * 24 * 3600


def _reset_at(now: datetime, seconds: int | None) -> datetime | None:
    if seconds is None:
        return None
    try:
        clamped = min(max(int(seconds), 0), MAX_RESET_SECONDS)
    except (TypeError, ValueError, OverflowError):
        return None
    return now + timedelta(seconds=clamped)


def quota_state_from(quota: Quota | None, now: datetime) -> QuotaState | None:
    if quota is None:
        return None
    reset_at = _reset_at(now, quota.reset_seconds)
    return QuotaState(limit=quota.limit, remaining=quota.remaining, reset_at=reset_at)


def exhausted(state: QuotaState | None, now: datetime) -> bool:
    return (
        state is not None
        and state.remaining == 0
        and state.reset_at is not None
        and state.reset_at > now
    )


def describe(state: QuotaState | None) -> str:
    if state is None or state.reset_at is None:
        return GENERIC_WORDING
    return f"quota used up until {state.reset_at.isoformat()}"


@dataclass
class Guarded:
    postings: list[Posting]
    state: QuotaState | None
    skipped: bool
    rate_limited: bool


async def guarded_search(
    store: QuotaStore | None,
    source: str,
    http: DiscoveryHttp,
    spec: SearchSpec,
    credentials: dict[str, str],
    *,
    now: Clock = _utcnow,
) -> Guarded:
    """Run one aggregator search behind the quota guard. Store errors never fail the search."""
    api_key = credentials.get("rapidapi_key", "")
    adapter: Any = get_aggregator(source)
    if store is None or not api_key:
        # No guard possible: let the adapter raise its own missing-credentials error.
        postings = await adapter.fetch_search(http, spec, credentials)
        return Guarded(postings, None, skipped=False, rate_limited=False)

    try:
        stored = await store.get(source, api_key)
    except Exception as exc:
        logger.warning(
            "quota store read failed (%s); continuing without the guard", type(exc).__name__
        )
        stored = None
    if exhausted(stored, now()):
        return Guarded([], stored, skipped=True, rate_limited=False)

    try:
        postings = await adapter.fetch_search(http, spec, credentials)
    except RateLimited as exc:
        quota = exc.quota
        reset_at = _reset_at(now(), quota.reset_seconds) if quota is not None else None
        limit = quota.limit if quota is not None else None
        await _put(
            store, source, api_key, QuotaState(limit, 0, reset_at or now() + DEFAULT_COOLDOWN)
        )
        # Without a reset header the caller gets the generic wording (reset_at None).
        return Guarded([], QuotaState(limit, 0, reset_at), skipped=False, rate_limited=True)

    state = quota_state_from(getattr(adapter, "quota", None), now())
    if state is not None:
        # A 200 that reports nothing left but no reset time must still stop further calls:
        # store the same one-hour estimate a 429 without a reset gets.
        stored = state
        if state.remaining == 0 and state.reset_at is None:
            stored = QuotaState(state.limit, 0, now() + DEFAULT_COOLDOWN)
        await _put(store, source, api_key, stored)
    return Guarded(postings, state, skipped=False, rate_limited=False)


async def _put(store: QuotaStore, source: str, api_key: str, state: QuotaState) -> None:
    try:
        await store.put(source, api_key, state)
    except Exception as exc:
        logger.warning("quota store write failed (%s); state not saved", type(exc).__name__)
