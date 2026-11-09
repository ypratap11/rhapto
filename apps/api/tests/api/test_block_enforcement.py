from __future__ import annotations

import time
import uuid

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import select, text

from rhapto.api import auth as auth_module
from rhapto.api.deps import AppState
from rhapto.db.models import User

EMAIL = "wife@example.com"
BLOCKED_MESSAGE = "This account has been blocked."
# SELECT statements one /me call by a normal access-mode user issues, captured from the code
# before the block check was added (the check reads an already-loaded attribute, so it must add none).
BASELINE_SELECT_COUNT = 3


@pytest.fixture
def access_app(app: FastAPI, monkeypatch) -> FastAPI:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = EMAIL
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = key.public_key()
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)
    app.state.test_key = key
    return app


def _headers(app: FastAPI) -> dict[str, str]:
    now = int(time.time())
    token = pyjwt.encode(
        {
            "email": EMAIL,
            "sub": "idp-sub-1",
            "aud": "test-aud",
            "iss": "https://test-team.cloudflareaccess.com",
            "iat": now,
            "exp": now + 300,
        },
        app.state.test_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    return {"Cf-Access-Jwt-Assertion": token}


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _block(session_factory, email: str = EMAIL) -> None:
    async with session_factory() as session:
        await session.execute(
            text("UPDATE users SET blocked_at = now() WHERE email = :e"), {"e": email}
        )
        await session.commit()


async def test_blocked_user_gets_403_account_blocked_on_next_request(
    access_app: FastAPI, session_factory
) -> None:
    async with _client(access_app) as c:
        assert (await c.get("/api/v1/me", headers=_headers(access_app))).status_code == 200
        await _block(session_factory)
        me = await c.get("/api/v1/me", headers=_headers(access_app))
        tailor = await c.post(f"/api/v1/jobs/{uuid.uuid4()}/tailor", headers=_headers(access_app))
    for response in (me, tailor):
        assert response.status_code == 403
        assert response.json()["code"] == "account_blocked"


async def test_unblocked_user_proceeds(access_app: FastAPI, session_factory) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        await _block(session_factory)
        async with session_factory() as session:
            await session.execute(text("UPDATE users SET blocked_at = NULL"))
            await session.commit()
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200


async def test_new_account_proceeds(access_app: FastAPI, session_factory) -> None:
    async with _client(access_app) as c:
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200
    async with session_factory() as session:
        row = await session.scalar(select(User).where(User.email == EMAIL))
    assert row is not None and row.blocked_at is None


async def test_blocked_request_writes_no_idp_subject(access_app: FastAPI, session_factory) -> None:
    async with _client(access_app) as c:
        # Create the account without a subject by seeding the row directly.
        async with session_factory() as session:
            session.add(User(email=EMAIL))
            await session.commit()
        await _block(session_factory)
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 403
    async with session_factory() as session:
        row = await session.scalar(select(User).where(User.email == EMAIL))
    assert row is not None and row.idp_subject is None


async def test_normal_request_issues_the_same_select_count_as_before(
    access_app: FastAPI, select_counter: list[str]
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))  # create the account
        select_counter.clear()
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    assert response.status_code == 200
    assert len(select_counter) == BASELINE_SELECT_COUNT


async def test_token_mode_never_blocks(
    app: FastAPI, client: httpx.AsyncClient, session_factory
) -> None:
    state: AppState = app.state.rhapto
    assert state.settings.rhapto_auth_mode == "token"
    async with session_factory() as session:
        await session.execute(
            text("UPDATE users SET blocked_at = now() WHERE id = :i"), {"i": state.user_id}
        )
        await session.commit()
    response = await client.get("/api/v1/me")
    assert response.status_code == 200


async def test_blocked_message_names_no_setting_or_address(
    access_app: FastAPI, session_factory
) -> None:
    async with _client(access_app) as c:
        await c.get("/api/v1/me", headers=_headers(access_app))
        await _block(session_factory)
        response = await c.get("/api/v1/me", headers=_headers(access_app))
    body = response.json()
    assert body["detail"] == BLOCKED_MESSAGE
    raw = response.text.lower()
    for forbidden in (EMAIL, "rhapto_", "env", "allowlist"):
        assert forbidden not in raw
