"""Admin action routes: reset-runs, block, unblock."""

from __future__ import annotations

import time
import uuid
from typing import Any

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api import auth as auth_module
from rhapto.db.models import AdminAction, User

ADMIN = "owner@example.com"
OTHER_ADMIN = "Second.Admin@Example.com"
ORIGIN = "https://rhapto.example.test"
V1 = "/api/v1/admin/users"


@pytest.fixture
def make_token():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())

    def make(email: str) -> str:
        return pyjwt.encode(
            {
                "email": email,
                "sub": f"sub-{email}",
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
    s.rhapto_allowed_emails = "victim@example.com"
    s.rhapto_admin_emails = f"{ADMIN}, {OTHER_ADMIN}"
    s.rhapto_web_origin = ORIGIN
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", make_token.cache)
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


async def _user(sf: async_sessionmaker[AsyncSession], email: str, runs: int = 0) -> uuid.UUID:
    async with sf() as s:
        u = User(email=email, trial_runs_used=runs)
        s.add(u)
        await s.commit()
        return u.id


async def _state(sf: async_sessionmaker[AsyncSession], uid: uuid.UUID) -> tuple[int, bool, int]:
    async with sf() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        n = await s.scalar(select(func.count()).select_from(AdminAction))
        return u.trial_runs_used, u.blocked_at is not None, int(n or 0)


async def _victim_id(sf: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sf() as s:
        return (
            await s.execute(select(User.id).where(User.email == "victim@example.com"))
        ).scalar_one()


async def test_reset_lowers_and_returns_new_value(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=3)
    r = await http.post(f"{V1}/{uid}/reset-runs", json={"to": 1}, headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json() == {"changed": True, "runs_used": 1, "blocked": None}
    assert r.headers["cache-control"] == "no-store"
    assert (await _state(session_factory, uid)) == (1, False, 1)


async def test_reset_raise_is_409_and_changes_nothing(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=1)
    r = await http.post(f"{V1}/{uid}/reset-runs", json={"to": 2}, headers=hdr)
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "only lower" in r.json()["detail"]
    assert (await _state(session_factory, uid)) == (1, False, 0)


async def test_reset_negative_is_422(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=1)
    r = await http.post(f"{V1}/{uid}/reset-runs", json={"to": -1}, headers=hdr)
    assert r.status_code == 422
    assert (await _state(session_factory, uid)) == (1, False, 0)


async def test_unknown_user_is_404(http, hdr) -> None:
    for path, body in [("reset-runs", {"to": 0}), ("block", None), ("unblock", None)]:
        r = await http.post(f"{V1}/{uuid.uuid4()}/{path}", json=body, headers=hdr)
        assert r.status_code == 404, path


async def test_block_then_user_gets_403_account_blocked(
    http, hdr, make_token, session_factory
) -> None:
    victim = {"Cf-Access-Jwt-Assertion": make_token("victim@example.com")}
    assert (await http.get("/api/v1/me", headers=victim)).status_code == 200
    uid = await _victim_id(session_factory)
    r = await http.post(f"{V1}/{uid}/block", headers=hdr)
    assert r.status_code == 200
    assert r.json() == {"changed": True, "runs_used": None, "blocked": True}
    blocked = await http.get("/api/v1/me", headers=victim)
    assert blocked.status_code == 403 and blocked.json()["code"] == "account_blocked"


async def test_unblock_restores_access(http, hdr, make_token, session_factory) -> None:
    victim = {"Cf-Access-Jwt-Assertion": make_token("victim@example.com")}
    assert (await http.get("/api/v1/me", headers=victim)).status_code == 200
    uid = await _victim_id(session_factory)
    await http.post(f"{V1}/{uid}/block", headers=hdr)
    r = await http.post(f"{V1}/{uid}/unblock", headers=hdr)
    assert r.status_code == 200
    assert r.json() == {"changed": True, "runs_used": None, "blocked": False}
    assert (await http.get("/api/v1/me", headers=victim)).status_code == 200


async def test_blocking_self_is_409(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, ADMIN)
    r = await http.post(f"{V1}/{uid}/block", headers=hdr)
    assert r.status_code == 409
    assert (await _state(session_factory, uid)) == (0, False, 0)


async def test_blocking_a_listed_admin_other_than_caller_is_409(http, hdr, session_factory) -> None:
    # Stored in a different case than the setting.
    uid = await _user(session_factory, "SECOND.ADMIN@example.com")
    r = await http.post(f"{V1}/{uid}/block", headers=hdr)
    assert r.status_code == 409
    assert (await _state(session_factory, uid)) == (0, False, 0)


def _routes(uid: uuid.UUID) -> list[tuple[str, Any]]:
    return [
        (f"{V1}/{uid}/reset-runs", {"to": 0}),
        (f"{V1}/{uid}/block", None),
        (f"{V1}/{uid}/unblock", None),
    ]


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
async def test_refused_origin_changes_nothing(origin, http, make_token, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=2)
    headers = {"Cf-Access-Jwt-Assertion": make_token(ADMIN)}
    if origin:
        headers["Origin"] = origin
    for path, body in _routes(uid):
        r = await http.post(path, json=body, headers=headers)
        assert r.status_code == 403, path
    assert (await _state(session_factory, uid)) == (2, False, 0)


async def test_non_admin_action_is_404_and_changes_nothing(
    http, make_token, session_factory
) -> None:
    uid = await _user(session_factory, "a@x.com", runs=2)
    headers = {"Cf-Access-Jwt-Assertion": make_token("victim@example.com"), "Origin": ORIGIN}
    for path, body in _routes(uid):
        r = await http.post(path, json=body, headers=headers)
        assert r.status_code == 404, path
    assert (await _state(session_factory, uid)) == (2, False, 0)


async def test_audit_row_records_the_caller_not_a_body_field(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=2)
    r = await http.post(
        f"{V1}/{uid}/reset-runs", json={"to": 0, "actor_email": "evil@x.com"}, headers=hdr
    )
    assert r.status_code == 200
    async with session_factory() as s:
        row = (await s.execute(select(AdminAction))).scalar_one()
    assert row.actor_email == ADMIN and row.action == "reset_runs"


async def test_double_post_writes_one_audit_row(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=2)
    first = await http.post(f"{V1}/{uid}/reset-runs", json={"to": 0}, headers=hdr)
    second = await http.post(f"{V1}/{uid}/reset-runs", json={"to": 0}, headers=hdr)
    assert first.json()["changed"] is True and second.json()["changed"] is False
    assert second.json()["runs_used"] == 0
    b1 = await http.post(f"{V1}/{uid}/block", headers=hdr)
    b2 = await http.post(f"{V1}/{uid}/block", headers=hdr)
    assert b1.json()["changed"] is True and b2.json()["changed"] is False
    assert b2.json()["blocked"] is True
    assert (await _state(session_factory, uid))[2] == 2


async def test_history_appears_on_user_detail_after_actions(http, hdr, session_factory) -> None:
    uid = await _user(session_factory, "a@x.com", runs=2)
    await http.post(f"{V1}/{uid}/reset-runs", json={"to": 1}, headers=hdr)
    await http.post(f"{V1}/{uid}/block", headers=hdr)
    detail = (await http.get(f"{V1}/{uid}", headers=hdr)).json()
    assert detail["blocked"] is True and detail["runs_used"] == 1
    assert {h["action"] for h in detail["history"]} == {"reset_runs", "block"}
    assert all(h["actor_email"] == ADMIN for h in detail["history"])
