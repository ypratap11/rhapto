# ruff: noqa: F811
from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine

from rhapto.api import deps
from tests.api.test_block_enforcement import EMAIL, _client, _headers, access_app  # noqa: F401


@pytest.fixture
def update_counter(engine: AsyncEngine) -> Iterator[list[str]]:
    """Every UPDATE of users.last_seen_at the app issues while the fixture is active."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        s = statement.lstrip().upper()
        if s.startswith("UPDATE USERS") and "LAST_SEEN_AT" in s:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)


async def _set_age(session_factory, hours: int) -> None:
    async with session_factory() as session:
        await session.execute(
            text("UPDATE users SET last_seen_at = now() - make_interval(hours => :h)"),
            {"h": hours},
        )
        await session.commit()


async def _age_seconds(session_factory) -> float:
    async with session_factory() as session:
        value = await session.scalar(
            text("SELECT extract(epoch FROM now() - last_seen_at) FROM users WHERE email = :e"),
            {"e": EMAIL},
        )
    return float(value)


async def test_first_request_with_stale_value_updates(
    access_app: FastAPI,
    session_factory,
    update_counter: list[str],
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))  # creates the account
        await _set_age(session_factory, 2)
        update_counter.clear()
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200
    assert len(update_counter) == 1
    assert await _age_seconds(session_factory) < 3600


async def test_two_requests_in_an_hour_write_once(
    access_app: FastAPI,
    session_factory,
    update_counter: list[str],
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        await _set_age(session_factory, 2)
        update_counter.clear()
        first = await c.get("/api/v1/me", headers=_headers(access_app))
        second = await c.get("/api/v1/me", headers=_headers(access_app))
    assert first.status_code == second.status_code == 200
    assert len(update_counter) == 1


async def test_fresh_value_issues_no_update(
    access_app: FastAPI,
    update_counter: list[str],
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        update_counter.clear()
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200
    assert update_counter == []


async def test_failing_update_does_not_fail_the_request(
    access_app: FastAPI,
    session_factory,
    monkeypatch,
    caplog,
) -> None:
    async def boom(session, user_id):  # type: ignore[no-untyped-def]
        raise RuntimeError("secret-detail-xyz")

    monkeypatch.setattr(deps, "touch_last_seen", boom)
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        await _set_age(session_factory, 2)
        with caplog.at_level(logging.WARNING):
            response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200
    assert "RuntimeError" in caplog.text
    assert "secret-detail-xyz" not in caplog.text
    assert EMAIL not in caplog.text


async def test_blocked_request_does_not_touch_last_seen(
    access_app: FastAPI,
    session_factory,
    update_counter: list[str],
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        await _set_age(session_factory, 2)
        async with session_factory() as session:
            await session.execute(text("UPDATE users SET blocked_at = now()"))
            await session.commit()
        update_counter.clear()
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 403
    assert update_counter == []
    assert await _age_seconds(session_factory) >= 2 * 3600 - 60
