from __future__ import annotations

import time

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from sqlalchemy import select

from rhapto.api import auth as auth_module
from rhapto.api.auth import is_allowed_email
from rhapto.api.deps import AppState
from rhapto.config import Settings
from rhapto.db.models import User


def test_exact_email_match() -> None:
    assert is_allowed_email("Wife@Example.com", "wife@example.com", "")


def test_domain_match() -> None:
    assert is_allowed_email("friend@company.io", "", "company.io")


def test_no_match_is_refused() -> None:
    assert not is_allowed_email("stranger@gmail.com", "wife@example.com", "company.io")


def test_empty_allowlist_fails_closed() -> None:
    assert not is_allowed_email("anyone@example.com", "", "")


# --- Integration tests: real Cloudflare Access JWT verification wired end to end ---
#
# Every test below mutates `state.settings` directly rather than restoring it afterwards. This is
# safe only because `app`/`api_settings` are function-scoped fixtures (tests/api/conftest.py:109,
# 145, per Task 1's verification), so each test gets its own fresh `Settings` and there is nothing
# to leak into the next test (plan-review minor 2).


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture
def signed_assertion(rsa_keypair):
    private_key, _ = rsa_keypair
    now = int(time.time())

    def make(email: str, *, aud: str = "test-aud", team: str = "test-team") -> str:
        return pyjwt.encode(
            {
                "email": email,
                "sub": "idp-sub-1",
                "aud": aud,
                "iss": f"https://{team}.cloudflareaccess.com",
                "iat": now,
                "exp": now + 300,
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )

    return make


async def test_valid_assertion_for_allowed_email_creates_an_account(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch
) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("Wife@Example.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 200
    assert response.json()["email"] == "wife@example.com"


async def test_non_allowlisted_email_gets_403_and_no_account(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("stranger@gmail.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 403
    async with session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == "stranger@gmail.com"))
    assert existing is None


async def test_duplicate_assertion_headers_is_400(app: FastAPI, signed_assertion) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    token = signed_assertion("wife@example.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        request = c.build_request(
            "GET",
            "/api/v1/me",
            headers=[("Cf-Access-Jwt-Assertion", token), ("Cf-Access-Jwt-Assertion", token)],
        )
        response = await c.send(request)
    assert response.status_code == 400


async def test_a_list_valued_aud_claim_is_accepted_when_it_contains_the_configured_aud(
    app: FastAPI, rsa_keypair, monkeypatch
) -> None:
    """Fixes plan-review I9: architecture.md §1.2 specifies 'aud contains RHAPTO_ACCESS_AUD', not
    'aud equals it' -- Cloudflare can issue a token whose aud is a list when an Access application
    is shared across more than one AUD tag. PyJWT's decode(audience=...) already checks membership
    against a list or scalar aud claim; this pins that behaviour rather than adding new logic."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    private_key, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    now = int(time.time())
    token = pyjwt.encode(
        {
            "email": "wife@example.com",
            "sub": "idp-sub-1",
            "aud": ["test-aud", "some-other-aud"],
            "iss": "https://test-team.cloudflareaccess.com",
            "iat": now,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 200


async def test_startup_refuses_empty_access_team_or_aud(
    api_settings: Settings, session_factory, storage
) -> None:
    """Fixes re-review I9: this is the actual code-level regression test the earlier resolution log
    claimed existed. Builds its own app (the `app` fixture's lifespan already ran with token-mode
    defaults before this test body runs) and asserts the lifespan itself refuses to start."""
    from asgi_lifespan import LifespanManager

    from rhapto.api.app import create_app

    api_settings.rhapto_auth_mode = "access"
    api_settings.rhapto_access_team = ""
    api_settings.rhapto_access_aud = ""
    api_settings.rhapto_allowed_emails = "wife@example.com"
    application = create_app(api_settings, session_factory=session_factory, storage=storage)
    with pytest.raises(RuntimeError, match="RHAPTO_ACCESS_TEAM and RHAPTO_ACCESS_AUD"):
        async with LifespanManager(application):
            pass
