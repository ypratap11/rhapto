"""Admin read routes: overview, user search, user detail."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api import auth as auth_module
from rhapto.api.deps import AppState
from rhapto.api.routers import admin as admin_router
from rhapto.db.models import (
    AdminAction,
    Answers,
    FeedbackRow,
    FreeSpend,
    LlmSettingsRow,
    ResumeBase,
    ResumeBlock,
    Task,
    User,
)
from rhapto.services.failure_categories import FailureCategory

ADMIN = "owner@example.com"
ORIGIN = "https://rhapto.example.test"
NOW = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
MARKER = "Wants more resumes"
TERM = "zzdistinctterm"


@pytest.fixture
def make_token():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())

    def make(email: str) -> str:
        return pyjwt.encode(
            {
                "email": email,
                "sub": "idp-sub-1",
                "aud": "test-aud",
                "iss": "https://test-team.cloudflareaccess.com",
                "iat": now,
                "exp": now + 300,
            },
            key,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )

    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = key.public_key()
    cache._fetched_at = time.monotonic()
    make.cache = cache  # type: ignore[attr-defined]
    return make


@pytest.fixture
def access_app(app: FastAPI, make_token, monkeypatch) -> FastAPI:
    s = app.state.rhapto.settings
    s.rhapto_auth_mode = "access"
    s.rhapto_access_team = "test-team"
    s.rhapto_access_aud = "test-aud"
    s.rhapto_allowed_emails = "someone@example.com"
    s.rhapto_admin_emails = ADMIN
    s.rhapto_web_origin = ORIGIN
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", make_token.cache)
    monkeypatch.setattr(admin_router, "_now", lambda: NOW)
    return app


@pytest.fixture
async def http(access_app: FastAPI):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=access_app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def hdr(make_token) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": make_token(ADMIN), "Origin": ORIGIN}


def _settings(app: FastAPI):
    state: AppState = app.state.rhapto
    return state.settings


async def _user(s: AsyncSession, email: str, *, runs: int = 0, **kw: Any) -> User:
    u = User(email=email, trial_runs_used=runs, **kw)
    s.add(u)
    await s.flush()
    return u


def _failed(u: User, error: str | None = None, finished: datetime = NOW - timedelta(hours=1)):
    return Task(
        user_id=u.id,
        type="tailor_job",
        status="failed",
        error=error,
        created_at=finished,
        finished_at=finished,
    )


def _wants_more(u: User) -> FeedbackRow:
    return FeedbackRow(
        user_id=u.id,
        form="quick",
        page_area="jobs",
        schema_version=1,
        answers={"kind": "idea", "text": f"{MARKER} please SENTINEL-feedback"},
        app_version="t",
    )


async def _seed_scenario(sf: async_sessionmaker[AsyncSession], name: str) -> None:
    async with sf() as s:
        if name == "budget":
            u = await _user(s, "b@x.com")
            s.add(
                FreeSpend(
                    user_id=u.id,
                    model="m",
                    cost_usd=Decimal("9"),
                    created_at=NOW - timedelta(hours=1),
                )
            )
        elif name == "duplicates":
            await _user(s, "d@x.com")
            await _user(s, "d+1@x.com")
        elif name == "failures":
            u = await _user(s, "f@x.com")
            s.add_all([_failed(u) for _ in range(5)])
        elif name == "ready_to_ask":
            u = await _user(s, "r@x.com", runs=3)
            s.add(_wants_more(u))
        elif name == "signin_limit":
            for i in range(40):
                await _user(s, f"u{i}@x.com")
        await s.commit()


@pytest.mark.parametrize(
    "scenario", ["budget", "duplicates", "failures", "ready_to_ask", "signin_limit", "clean"]
)
async def test_overview_shape_and_alerts_fire_on_seeded_data(
    http, hdr, session_factory, access_app, scenario
) -> None:
    _settings(access_app).rhapto_monthly_free_budget_usd = 10.0
    await _seed_scenario(session_factory, scenario)
    r = await http.get("/api/v1/admin/overview", headers=hdr)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "signups_total",
        "signups_today",
        "free_spend_month_usd",
        "budget_usd",
        "accounts",
        "account_cap",
        "want_more_users",
        "failed_7d",
        "alerts",
    }
    ids = [a["id"] for a in body["alerts"]]
    assert ids == ([] if scenario == "clean" else [scenario])
    assert body["budget_usd"] == 10.0
    assert isinstance(body["free_spend_month_usd"], str)
    if scenario == "signin_limit":
        assert body["accounts"] >= 40 and body["account_cap"] == 50
    if scenario == "failures":
        assert body["failed_7d"] == 5
        assert "Other" in body["alerts"][0]["detail"]


async def test_overview_budget_disabled_says_no_budget(
    http, hdr, session_factory, access_app
) -> None:
    assert _settings(access_app).rhapto_monthly_free_budget_usd < 0
    await _seed_scenario(session_factory, "budget")
    r = await http.get("/api/v1/admin/overview", headers=hdr)
    assert r.json()["budget_usd"] is None
    assert [a["id"] for a in r.json()["alerts"]] == []


async def test_user_detail_404_for_unknown_id_is_the_standard_not_found_for_admins(
    http, hdr
) -> None:
    r = await http.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=hdr)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["status"] == 404


async def test_search_rejects_offset_over_10000(http, hdr) -> None:
    r = await http.post("/api/v1/admin/users/search", json={"q": "", "offset": 10001}, headers=hdr)
    assert r.status_code == 422
    ok = await http.post("/api/v1/admin/users/search", json={"q": "", "offset": 10000}, headers=hdr)
    assert ok.status_code == 200
    neg = await http.post("/api/v1/admin/users/search", json={"offset": -1}, headers=hdr)
    assert neg.status_code == 422


async def test_search_rejects_q_longer_than_320(http, hdr) -> None:
    r = await http.post("/api/v1/admin/users/search", json={"q": "a" * 321}, headers=hdr)
    assert r.status_code == 422
    ok = await http.post("/api/v1/admin/users/search", json={"q": "a" * 320}, headers=hdr)
    assert ok.status_code == 200


async def test_search_returns_rows_and_pages(http, hdr, session_factory) -> None:
    async with session_factory() as s:
        for i in range(26):
            await _user(s, f"p{i:02}@x.com")
        await s.commit()
    first = (await http.post("/api/v1/admin/users/search", json={}, headers=hdr)).json()
    assert len(first["users"]) == 25 and first["next_offset"] == 25
    assert set(first["users"][0]) == {
        "id",
        "email",
        "runs_used",
        "runs_limit",
        "failed_count",
        "last_seen_at",
        "blocked",
    }
    assert first["users"][0]["runs_limit"] == 3
    second = (
        await http.post("/api/v1/admin/users/search", json={"offset": 25}, headers=hdr)
    ).json()
    assert len(second["users"]) == 2 and second["next_offset"] is None  # 26 + bootstrap user


async def test_get_search_is_not_a_route(http, hdr, make_token, monkeypatch) -> None:
    called: list[bool] = []
    from rhapto.db.repositories import admin as repo

    real = repo.search_users

    async def spy(*a: Any, **k: Any):
        called.append(True)
        return await real(*a, **k)

    monkeypatch.setattr(repo, "search_users", spy)
    r = await http.get("/api/v1/admin/users/search", headers=hdr)
    assert r.status_code != 200
    assert called == []
    other = {"Cf-Access-Jwt-Assertion": make_token("x@example.com")}
    stranger = await http.get("/api/v1/admin/users/search", headers=other)
    unknown = await http.get("/api/v1/definitely-unknown", headers=other)
    assert (stranger.status_code, stranger.content) == (unknown.status_code, unknown.content)


async def _seed_sentinels(sf: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sf() as s:
        u = await _user(s, "sent@x.com", runs=3)
        s.add(_failed(u, "EngineError: SENTINEL-tasks-error"))
        s.add(_wants_more(u))
        s.add(
            LlmSettingsRow(
                user_id=u.id, provider="anthropic", model="m", api_key_encrypted="SENTINEL-key"
            )
        )
        s.add(
            ResumeBlock(
                user_id=u.id, block_id="b1", type="bullet", content="SENTINEL-block", verified=True
            )
        )
        s.add(ResumeBase(user_id=u.id, base_id="base", name="SENTINEL-profile-name"))
        s.add(Answers(user_id=u.id, answers_json={"q": "SENTINEL-answer"}))
        await s.commit()
        return u.id


async def test_no_sentinel_reaches_any_admin_response(http, hdr, session_factory) -> None:
    uid = await _seed_sentinels(session_factory)
    responses = [
        await http.get("/api/v1/admin/overview", headers=hdr),
        await http.post("/api/v1/admin/users/search", json={"q": "sent"}, headers=hdr),
        await http.get(f"/api/v1/admin/users/{uid}", headers=hdr),
        await http.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=hdr),
        await http.get("/api/v1/admin/session", headers=hdr),
    ]
    for r in responses:
        assert "SENTINEL" not in r.text
        assert "SENTINEL" not in str(dict(r.headers))
    assert responses[2].status_code == 200


async def test_failure_category_is_enum_value_only(http, hdr, session_factory) -> None:
    uid = await _seed_sentinels(session_factory)
    r = await http.get(f"/api/v1/admin/users/{uid}", headers=hdr)
    body = r.json()
    f = body["failures"][0]
    assert f["category"] in {c.value for c in FailureCategory}
    assert f["category"] == "provider_error"
    assert set(f) == {"when", "type", "category", "label"}
    assert "error" not in body
    assert body["asked_for_more"] is True


async def test_stale_running_task_shows_as_did_not_finish(http, hdr, session_factory) -> None:
    async with session_factory() as s:
        u = await _user(s, "stale@x.com")
        s.add(
            Task(
                user_id=u.id,
                type="tailor_job",
                status="running",
                created_at=NOW - timedelta(hours=1),
            )
        )
        await s.commit()
        uid = u.id
    r = await http.get(f"/api/v1/admin/users/{uid}", headers=hdr)
    assert r.json()["failures"][0]["category"] == "did_not_finish"


async def test_no_email_or_term_in_log_records(http, hdr, session_factory, caplog) -> None:
    async with session_factory() as s:
        u = await _user(s, f"{TERM}@x.com")
        s.add(_failed(u, "EngineError: x"))
        await s.commit()
        uid = u.id
    caplog.set_level(logging.DEBUG)
    r1 = await http.post("/api/v1/admin/users/search", json={"q": TERM}, headers=hdr)
    r2 = await http.get(f"/api/v1/admin/users/{uid}", headers=hdr)
    assert r1.status_code == r2.status_code == 200
    for rec in caplog.records:
        blob = rec.getMessage() + repr(rec.args) + repr(rec.msg)
        assert TERM not in blob and "@x.com" not in blob


async def test_every_get_leaves_admin_actions_unchanged(http, hdr, session_factory) -> None:
    uid = await _seed_sentinels(session_factory)

    async def count() -> int:
        async with session_factory() as s:
            return int(await s.scalar(select(func.count()).select_from(AdminAction)) or 0)

    before = await count()
    await http.get("/api/v1/admin/overview", headers=hdr)
    await http.post("/api/v1/admin/users/search", json={}, headers=hdr)
    await http.get(f"/api/v1/admin/users/{uid}", headers=hdr)
    await http.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=hdr)
    assert await count() == before


async def test_responses_are_no_store(http, hdr) -> None:
    for r in [
        await http.get("/api/v1/admin/overview", headers=hdr),
        await http.post("/api/v1/admin/users/search", json={}, headers=hdr),
        await http.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=hdr),
        await http.post("/api/v1/admin/users/search", json={"offset": -5}, headers=hdr),
    ]:
        assert r.headers["cache-control"] == "no-store"
