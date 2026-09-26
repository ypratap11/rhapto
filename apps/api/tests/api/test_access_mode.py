from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
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


def test_bare_at_sign_domain_entry_does_not_match_an_address_with_no_at_sign() -> None:
    """M10 regression: a domains entry of exactly "@" used to normalize to "" (the emptiness
    filter ran before `lstrip("@")`), and "" then matched any email containing no "@" at all."""
    assert not is_allowed_email("attacker", "", "@")
    assert not is_allowed_email("attacker", "", "@, @")


def test_a_second_at_sign_does_not_smuggle_a_different_domain_past_the_check() -> None:
    """M10 regression: 'a@evil.com@company.io' must not be admitted for domain 'company.io' --
    `rsplit("@", 1)` alone would take the substring after the LAST "@", which is not how any mail
    system parses an address with two "@" characters."""
    assert not is_allowed_email("a@evil.com@company.io", "", "company.io")


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


async def test_startup_refuses_when_the_allowlist_itself_is_empty(
    api_settings: Settings, session_factory, storage
) -> None:
    """I6 regression: an empty allowlist is a distinct, earlier failure than "no matching row" --
    on a fresh install with an empty `users` table, the two causes are otherwise
    indistinguishable, and the fresh-install operator needs a different next step (boot once in
    token mode first) than the owner-email-mismatch operator (`accounts set-email`)."""
    from asgi_lifespan import LifespanManager

    from rhapto.api.app import create_app

    api_settings.rhapto_auth_mode = "access"
    api_settings.rhapto_access_team = "test-team"
    api_settings.rhapto_access_aud = "test-aud"
    api_settings.rhapto_allowed_emails = ""
    api_settings.rhapto_allowed_email_domains = ""
    application = create_app(api_settings, session_factory=session_factory, storage=storage)
    with pytest.raises(RuntimeError, match="neither RHAPTO_ALLOWED_EMAILS nor"):
        async with LifespanManager(application):
            pass


# --- C2: the empty-allowlist gate, exercised end to end (not just the pure function) ---


async def test_empty_allowlist_end_to_end_is_403_and_no_account(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    """C2 (Critical): the only prior empty-allowlist assertion was the pure-function
    `test_empty_allowlist_fails_closed` above, which a wiring-level regression at the call site
    (`deps.py`) walks straight past -- the pure function can be correct while the branch that
    calls it is not. This exercises the real HTTP path end to end, the same shape as
    `test_non_allowlisted_email_gets_403_and_no_account`.

    Break-then-restore performed: changing `deps.py`'s guard to
    `if (settings.rhapto_allowed_emails or settings.rhapto_allowed_email_domains) and not
    is_allowed_email(...)` -- "unconfigured means open" -- makes this test fail (200 instead of
    403, and a `users` row gets created); restored afterwards and confirmed green again."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = ""
    state.settings.rhapto_allowed_email_domains = ""

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("anyone@example.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 403
    async with session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == "anyone@example.com"))
    assert existing is None


async def test_domain_allowlist_admits_a_matching_email_end_to_end(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch
) -> None:
    """C2: RHAPTO_ALLOWED_EMAIL_DOMAINS had no coverage at all before this -- every other
    access-mode integration test in this file sets `rhapto_allowed_emails` only."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = ""
    state.settings.rhapto_allowed_email_domains = "example.com"

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("new-hire@example.com")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 200
    assert response.json()["email"] == "new-hire@example.com"


# --- C1: signature verification itself, proven by forging exactly what a bypass would accept ---


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _forge_hs256(header: dict[str, object], payload: dict[str, object], secret: bytes) -> str:
    """Hand-assembles a JWT rather than calling PyJWT's own `encode()`, which refuses to build
    this: `jwt.encode(payload, pem_bytes, algorithm="HS256")` raises `InvalidKeyError` because
    PyJWT detects the "key" looks like an asymmetric key (verified against installed PyJWT 2.13.0).
    An attacker forging their own token has no such guard, so this reproduces what one would
    actually send: HS256, signed with the RSA public key's PEM bytes used as the HMAC secret --
    the classic RS256-to-HS256 confusion attack, viable only if `algorithms` were ever widened
    past `["RS256"]` or signature verification were ever disabled."""
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(secret, f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"


def _forge_alg_none(payload: dict[str, object], *, kid: str = "test-kid") -> str:
    header = {"alg": "none", "kid": kid, "typ": "JWT"}
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    return f"{header_b64}.{payload_b64}."  # alg:none tokens carry an empty signature segment


def _access_claims(email: str, *, sub: str = "attacker-sub") -> dict[str, object]:
    now = int(time.time())
    return {
        "email": email,
        "sub": sub,
        "aud": "test-aud",
        "iss": "https://test-team.cloudflareaccess.com",
        "iat": now,
        "exp": now + 300,
    }


def _install_test_team_cache(monkeypatch, public_key) -> None:
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)


async def test_assertion_signed_by_a_different_key_is_rejected(
    app: FastAPI, rsa_keypair, monkeypatch
) -> None:
    """C1(a) (Critical): a token whose `kid` claims the cached key but whose signature was
    actually produced by a *different* private key must be rejected -- this is what "signature
    actually checked" means, as opposed to "kid present in the JWKS".

    Break-then-restore performed: adding `"verify_signature": False` to the `options` dict passed
    to `jwt.decode` in `auth.py` makes this test fail (200 instead of 401, verified directly
    against the installed PyJWT: the forged claims decode successfully with signature checking
    off); restored afterwards and confirmed green (and `uv run mypy src` clean) again."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    _, public_key = rsa_keypair
    _install_test_team_cache(monkeypatch, public_key)

    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = pyjwt.encode(
        _access_claims("wife@example.com"),
        attacker_key,  # NOT the key the cache holds under "test-kid"
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401


async def test_forged_hs256_using_the_public_key_pem_as_hmac_secret_is_rejected(
    app: FastAPI, rsa_keypair, monkeypatch
) -> None:
    """C1(b) (Critical): the classic RS256-to-HS256 confusion attack. `algorithms=["RS256"]`
    must reject this outright regardless of what "key" object `key_for` supplies.

    Break-then-restore performed: same mutation as C1(a) (`"verify_signature": False`) makes this
    forged token decode successfully (verified directly against installed PyJWT: with signature
    checking off, PyJWT does not re-derive or check the alg-vs-key relationship either); restored
    afterwards and confirmed green again."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    private_key, public_key = rsa_keypair
    _install_test_team_cache(monkeypatch, public_key)
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    header = {"alg": "HS256", "kid": "test-kid", "typ": "JWT"}
    token = _forge_hs256(header, _access_claims("wife@example.com"), pem)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401


async def test_alg_none_assertion_is_rejected(app: FastAPI, rsa_keypair, monkeypatch) -> None:
    """C1(c) (Critical): the classic "alg: none" bypass, carrying an empty signature segment.

    Break-then-restore performed: same mutation as C1(a)/(b) (`"verify_signature": False`) makes
    this forged token decode successfully (verified directly against installed PyJWT); restored
    afterwards and confirmed green again."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    _, public_key = rsa_keypair
    _install_test_team_cache(monkeypatch, public_key)
    token = _forge_alg_none(_access_claims("wife@example.com"))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401


# --- I3, I4: the JWKS cache's failure and rotation handling ---


async def test_a_key_dropped_by_a_successful_refresh_is_not_accepted_from_the_retained_set(
    monkeypatch,
) -> None:
    """I3 regression: architecture.md §1.3 reserves the retained set for when a refresh FAILS (an
    unreachable JWKS host), not for a key a *successful* refresh rotated out on purpose. Before the
    fix, the retained lookup in `key_for` was unconditional, so a key Cloudflare rotated out was
    still accepted on the very request whose successful refresh dropped it."""
    cache = auth_module.JwksCache("http://unused", ttl_seconds=0, refetch_floor=0)
    cache._keys = {"old-kid": "old-key-object"}
    cache._fetched_at = time.monotonic() - 1  # already past the zero TTL: forces a refresh attempt

    async def fake_successful_refresh(self: auth_module.JwksCache) -> None:
        # A real, successful refresh that rotated "old-kid" out on purpose.
        self._retained = self._keys
        self._keys = {"new-kid": "new-key-object"}
        self._fetched_at = time.monotonic()
        self._last_refresh_failed = False

    monkeypatch.setattr(auth_module.JwksCache, "_refresh", fake_successful_refresh)

    with pytest.raises(HTTPException) as exc_info:
        await cache.key_for("old-kid")
    assert exc_info.value.status_code == 503


async def test_an_unparseable_jwks_response_is_a_503_not_a_500(monkeypatch) -> None:
    """I4 regression: a non-JSON JWKS body (or a JWK `_refresh` cannot parse) must land in the
    same "cannot verify identity right now" path as a network failure, not escape `key_for`
    entirely as an unhandled exception. Before the fix, `key_for` caught only `httpx.HTTPError`."""
    cache = auth_module.JwksCache("http://unused", refetch_floor=0)

    class _BadResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> None:
            raise ValueError("not JSON")

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def get(self, url: str) -> _BadResponse:
            return _BadResponse()

    monkeypatch.setattr(auth_module.httpx, "AsyncClient", lambda timeout=5.0: _FakeClient())

    with pytest.raises(HTTPException) as exc_info:
        await cache.key_for("some-kid")
    assert exc_info.value.status_code == 503


# --- I5: the verified `sub` claim is stored on `users.idp_subject`, and never overwritten ---


async def test_verified_sub_is_stored_on_first_sign_in_and_never_overwritten(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    private_key, public_key = rsa_keypair
    _install_test_team_cache(monkeypatch, public_key)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get(
            "/api/v1/me",
            headers={"Cf-Access-Jwt-Assertion": signed_assertion("wife@example.com")},
        )
    assert response.status_code == 200
    async with session_factory() as session:
        stored = await session.scalar(select(User).where(User.email == "wife@example.com"))
    assert stored is not None
    assert stored.idp_subject == "idp-sub-1"  # signed_assertion's fixed "sub" claim

    # A second sign-in claiming a DIFFERENT sub must not overwrite the first -- the column is
    # UNIQUE, and Access can reissue a `sub`, so an unconditional overwrite risks colliding with
    # a value already claimed elsewhere.
    other_sub_token = pyjwt.encode(
        _access_claims("wife@example.com", sub="a-different-sub"),
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": other_sub_token})
    assert response.status_code == 200
    async with session_factory() as session:
        stored_again = await session.scalar(select(User).where(User.email == "wife@example.com"))
    assert stored_again is not None
    assert stored_again.idp_subject == "idp-sub-1"  # unchanged


# --- M11, M12: malformed claims/header fields, not signature-level attacks ---


async def test_a_non_string_email_claim_is_rejected(app: FastAPI, rsa_keypair, monkeypatch) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    private_key, public_key = rsa_keypair
    _install_test_team_cache(monkeypatch, public_key)

    claims = _access_claims("wife@example.com")
    claims["email"] = ["wife@example.com", "x@y.z"]  # list-valued, not a string
    token = pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401


async def test_assertion_with_no_kid_is_401(app: FastAPI, rsa_keypair) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    private_key, _ = rsa_keypair
    token = pyjwt.encode(
        _access_claims("wife@example.com"), private_key, algorithm="RS256"
    )  # no "kid" in the header at all

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 401
