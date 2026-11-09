from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from sqlalchemy import select

from rhapto.api import auth as auth_module
from rhapto.api.admin_guard import AdminRoute
from rhapto.api.deps import AppState
from rhapto.api.routers import admin
from rhapto.db.models import User

ADMIN = "Owner@Example.com"
ORIGIN = "https://rhapto.example.test"
EXPECTED_ADMIN_ROUTES = 2  # session + catch-all; Task 11 raises this to 5, Task 12 to 8
UNKNOWN = "/api/v1/definitely-unknown"
PROBE_POST = "/api/v1/adminprobe/echo"


class _Body(BaseModel):
    name: str


def _probe_router() -> APIRouter:
    """Test-only POST route: no real admin POST exists yet. Mounted at its own prefix because the
    real catch-all would otherwise win (first full match)."""
    probe = APIRouter(prefix="/adminprobe", route_class=AdminRoute)

    async def echo(body: _Body) -> dict[str, str]:
        return {"name": body.name}

    probe.add_api_route("/echo", echo, methods=["POST"])
    return probe


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
    state: AppState = app.state.rhapto
    s = state.settings
    s.rhapto_auth_mode = "access"
    s.rhapto_access_team = "test-team"
    s.rhapto_access_aud = "test-aud"
    s.rhapto_allowed_emails = "someone@example.com"
    s.rhapto_admin_emails = ADMIN
    s.rhapto_web_origin = ORIGIN
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", make_token.cache)
    app.include_router(_probe_router(), prefix="/api/v1")
    return app


@pytest.fixture
async def http(access_app: FastAPI):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=access_app), base_url="http://test"
    ) as c:
        yield c


def _hdr(token: str, **extra: str) -> dict[str, str]:
    return {"Cf-Access-Jwt-Assertion": token, **extra}


async def _unknown_body(http: httpx.AsyncClient, make_token) -> tuple[int, bytes]:
    r = await http.get(UNKNOWN, headers=_hdr(make_token("x@example.com")))
    assert r.status_code == 404
    return r.status_code, r.content


# ---- enumeration -------------------------------------------------------------------------------


def test_every_admin_route_is_an_admin_route() -> None:
    # `admin.router.routes`, never `app.routes`: that holds lazy include objects with no `path`.
    routes = admin.router.routes
    assert routes, "no admin routes found: the enumeration would be vacuous"
    for route in routes:
        assert isinstance(route, AdminRoute), route
    assert len(routes) == EXPECTED_ADMIN_ROUTES


async def test_admin_router_is_mounted(http: httpx.AsyncClient, make_token) -> None:
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_every_admin_route_answers_non_admin_with_the_unknown_path_404(
    http: httpx.AsyncClient, make_token
) -> None:
    expected = await _unknown_body(http, make_token)
    seen = 0
    for route in admin.router.routes:
        path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), route.path)  # type: ignore[attr-defined]
        for method in sorted(route.methods):  # type: ignore[attr-defined]
            r = await http.request(
                method, f"/api/v1{path}", headers=_hdr(make_token("x@example.com"))
            )
            assert (r.status_code, r.content) == expected, (method, path)
            seen += 1
    assert seen >= 6


def test_admin_routes_are_not_in_the_public_openapi(app: FastAPI) -> None:
    doc = app.openapi()
    assert not [p for p in doc["paths"] if "/admin" in p]
    assert not [n for n in doc.get("components", {}).get("schemas", {}) if n.startswith("Admin")]


async def test_openapi_endpoint_anonymous_has_no_admin(anon_client: httpx.AsyncClient) -> None:
    r = await anon_client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert "admin" not in r.text.lower()


def test_no_other_router_mentions_admin_paths() -> None:
    routers = Path(admin.__file__).parent
    others = [p for p in routers.glob("*.py") if p.name != "admin.py"]
    assert others
    assert [p.name for p in others if "/admin" in p.read_text("utf-8")] == []


# ---- identical 404 -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "valid non-admin jwt",
        "token mode",
        "no assertion",
        "invalid assertion",
        "malformed json",
        "bad uuid in path",
        "wrong method",
    ],
)
async def test_non_admin_body_is_identical_to_unknown_path(
    case: str, http: httpx.AsyncClient, access_app: FastAPI, make_token
) -> None:
    expected = await _unknown_body(http, make_token)
    non_admin = _hdr(make_token("x@example.com"))
    if case == "valid non-admin jwt":
        r = await http.get("/api/v1/admin/session", headers=non_admin)
    elif case == "token mode":
        access_app.state.rhapto.settings.rhapto_auth_mode = "token"
        r = await http.get("/api/v1/admin/session", headers={"Authorization": "Bearer t"})
    elif case == "no assertion":
        r = await http.get("/api/v1/admin/session")
    elif case == "invalid assertion":
        r = await http.get("/api/v1/admin/session", headers=_hdr("not.a.jwt"))
    elif case == "malformed json":
        r = await http.post(
            PROBE_POST,
            content=b"{not json",
            headers={**non_admin, "Content-Type": "application/json"},
        )
    elif case == "bad uuid in path":
        r = await http.get("/api/v1/admin/users/not-a-uuid", headers=non_admin)
    else:
        r = await http.put("/api/v1/admin/session", headers=non_admin)
    assert (r.status_code, r.content) == expected


# ---- no database -------------------------------------------------------------------------------


async def test_guard_runs_no_sql(
    http: httpx.AsyncClient, make_token, select_counter: list[str]
) -> None:
    select_counter.clear()
    await http.get("/api/v1/admin/session", headers=_hdr(make_token("x@example.com")))
    await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert select_counter == []


async def test_admin_with_no_users_row_gets_session_200(
    http: httpx.AsyncClient, make_token, session_factory
) -> None:
    async with session_factory() as session:
        assert await session.scalar(select(User).where(User.email == ADMIN.casefold())) is None
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert r.status_code == 200


# ---- who is admin ------------------------------------------------------------------------------


async def test_case_difference_is_admin(http: httpx.AsyncClient, make_token) -> None:
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN.upper())))
    assert r.status_code == 200


async def test_empty_setting_is_404_for_everyone(
    http: httpx.AsyncClient, access_app: FastAPI, make_token
) -> None:
    access_app.state.rhapto.settings.rhapto_admin_emails = ""
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert r.status_code == 404


async def test_address_admitted_only_by_invite_domain_is_404(
    http: httpx.AsyncClient, access_app: FastAPI, make_token
) -> None:
    access_app.state.rhapto.settings.rhapto_allowed_email_domains = "invite.example"
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token("guest@invite.example")))
    assert r.status_code == 404


async def test_jwks_unreachable_is_503(http: httpx.AsyncClient, make_token, monkeypatch) -> None:
    async def boom(self: auth_module.JwksCache) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth_module.JwksCache, "_refresh", boom)
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", auth_module.JwksCache("http://x"))
    r = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert r.status_code == 503
    assert r.headers["cache-control"] == "no-store"


async def test_session_response_is_no_store(http: httpx.AsyncClient, make_token) -> None:
    ok = await http.get("/api/v1/admin/session", headers=_hdr(make_token(ADMIN)))
    assert ok.headers["cache-control"] == "no-store"
    miss = await http.get("/api/v1/admin/nope", headers=_hdr(make_token(ADMIN)))
    assert miss.status_code == 404
    assert miss.headers["cache-control"] == "no-store"


# ---- Origin ------------------------------------------------------------------------------------


def _post(http: httpx.AsyncClient, token: str, origin: str | None):
    headers = _hdr(token)
    if origin is not None:
        headers["Origin"] = origin
    return http.post(PROBE_POST, json={"name": "a"}, headers=headers)


async def test_post_with_matching_origin_succeeds(http: httpx.AsyncClient, make_token) -> None:
    assert (await _post(http, make_token(ADMIN), ORIGIN)).status_code == 200


async def test_post_without_origin_is_403(http: httpx.AsyncClient, make_token) -> None:
    assert (await _post(http, make_token(ADMIN), None)).status_code == 403


async def test_post_with_foreign_origin_is_403(http: httpx.AsyncClient, make_token) -> None:
    assert (await _post(http, make_token(ADMIN), "https://evil.example")).status_code == 403


async def test_post_with_two_origin_values_is_403(http: httpx.AsyncClient, make_token) -> None:
    r = await http.post(
        PROBE_POST,
        json={"name": "a"},
        headers=[  # type: ignore[arg-type]
            ("Cf-Access-Jwt-Assertion", make_token(ADMIN)),
            ("Origin", ORIGIN),
            ("Origin", ORIGIN),
        ],
    )
    assert r.status_code == 403


async def test_post_with_trailing_slash_origin_setting_matches(
    http: httpx.AsyncClient, access_app: FastAPI, make_token
) -> None:
    access_app.state.rhapto.settings.rhapto_web_origin = ORIGIN + "/"
    assert (await _post(http, make_token(ADMIN), ORIGIN)).status_code == 200


async def test_non_admin_post_with_foreign_origin_is_404(
    http: httpx.AsyncClient, make_token
) -> None:
    expected = await _unknown_body(http, make_token)
    r = await _post(http, make_token("x@example.com"), "https://evil.example")
    assert (r.status_code, r.content) == expected
