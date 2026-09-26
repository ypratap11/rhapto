from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Literal

import httpx
import jwt
from fastapi import Header, HTTPException, Request
from jwt.exceptions import PyJWTError

if TYPE_CHECKING:
    from rhapto.api.deps import AppState

AuthMode = Literal["token", "access"]


def _state(request: Request) -> AppState:
    """Reads the same `request.app.state.rhapto` attribute `deps.get_state` reads, without
    importing `deps.py` (which imports this module) -- see the C1 fix note above."""
    return request.app.state.rhapto  # type: ignore[no-any-return]


@dataclass(frozen=True)
class Principal:
    """Who made this request, resolved before `current_user` maps it to a `users.id`.

    `subject` is the literal string "token" in token mode (there is no per-request subject, only
    the one instance secret) and the IdP `sub` claim in access mode (Task 3). `email` is always
    casefolded and is the identity key in both modes.
    """

    mode: AuthMode
    subject: str
    email: str


def is_allowed_email(email: str, allowed_emails: str, allowed_domains: str) -> bool:
    """Casefolded exact-match or domain-match against the two comma-separated allowlists.

    An empty allowlist fails closed: "unconfigured" must never mean "open", matching the
    codebase's existing posture on an empty `rhapto_api_token`.
    """
    normalized = email.casefold().strip()
    exact = {e.strip().casefold() for e in allowed_emails.split(",") if e.strip()}
    # The emptiness check must run AFTER `lstrip("@")`, not before: a domains entry of exactly "@"
    # is truthy at `d.strip()` and only becomes "" once the leading "@" is stripped. Checking
    # truthiness before the strip (the earlier form of this function) let a bare "@" domain entry
    # normalize to "", which then matched every email with no "@" in it at all -- an auth bypass
    # (verified: `is_allowed_email("attacker", "", "@")` was `True`).
    domains: set[str] = set()
    for d in allowed_domains.split(","):
        stripped = d.strip().casefold().lstrip("@")
        if stripped:
            domains.add(stripped)
    if not exact and not domains:
        return False
    if normalized in exact:
        return True
    # Exactly one "@" required before domain-matching: without this, an email like
    # "a@evil.com@company.io" would `rsplit("@", 1)` to domain "company.io" and be admitted, even
    # though the real domain (by any mail-parsing rule) is "evil.com".
    if normalized.count("@") != 1:
        return False
    local, domain = normalized.split("@", 1)
    # A non-empty local part required too: "@example.com" alone (no IdP issues this, but nothing
    # upstream rules it out either) would otherwise still satisfy `count("@") == 1` and match
    # domain "example.com".
    if not local:
        return False
    return domain in domains


class JwksCache:
    """Per-process JWKS cache with last-good-key retention (architecture.md §1.3).

    An unreachable JWKS endpoint does not fail requests as long as the *retained* set (the last
    successfully fetched one) still has the requested `kid` -- Cloudflare rotates keys with
    overlap, so a retained set stays valid far longer than any plausible outage. Only when the
    retained set also lacks the `kid` does this raise, and the caller turns that into a 503 (not
    401): "we cannot check" is not "you are not authorised".

    Critically, the retained set is consulted only when the most recent *attempted* refresh
    failed (`_last_refresh_failed`), never after a refresh that succeeded. A successful refresh
    that simply doesn't include `kid` means Cloudflare rotated that key out on purpose -- that is
    architecture §1.3's "the fetch fails" case's opposite, and accepting a retained key there would
    keep a rotated-out key trusted for up to `refetch_floor` seconds after the very refresh that
    dropped it.
    """

    def __init__(
        self, jwks_url: str, *, ttl_seconds: float = 600, refetch_floor: float = 30
    ) -> None:
        self._jwks_url = jwks_url
        self._ttl = ttl_seconds
        self._floor = refetch_floor
        self._keys: dict[str, Any] = {}  # the last successfully fetched set
        self._retained: dict[str, Any] = {}  # the set before that, kept only as a fallback
        self._fetched_at: float = 0.0  # set only on a successful fetch
        self._last_attempt_at: float = 0.0  # set on every attempt, success or failure
        # True only when the most recently *attempted* refresh raised -- left unchanged by a
        # rate-limited call that skips fetching entirely (the `_floor` early return below), so a
        # sustained outage is still recognised as such on every request during the floor window,
        # not just the one that happened to trigger the failing HTTP call.
        self._last_refresh_failed: bool = False

    async def _refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_attempt_at < self._floor:
            return
        self._last_attempt_at = now
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
            fetched: dict[str, Any] = {}
            for jwk in response.json().get("keys", []):
                kid = jwk.get("kid")
                if kid:
                    fetched[kid] = jwt.PyJWK(jwk).key
        if self._keys:
            self._retained = self._keys
        self._keys = fetched
        self._fetched_at = now
        self._last_refresh_failed = False  # this attempt succeeded; the current set is trustworthy

    async def key_for(self, kid: str) -> Any:
        now = time.monotonic()
        if kid not in self._keys or now - self._fetched_at > self._ttl:
            try:
                await self._refresh()
            # A non-JSON JWKS body (`response.json()` above) or a JWK `_refresh` cannot parse
            # (`jwt.PyJWK(jwk).key` above) must land here too, not escape as a 500 -- both are
            # "we cannot check", the same as an unreachable host. `json.JSONDecodeError`
            # specifically, not a bare `ValueError`: the latter would also swallow a genuine
            # programming error elsewhere in this block and misreport it as a transient,
            # Retry-After-able 503 instead of surfacing it during an incident.
            except (httpx.HTTPError, json.JSONDecodeError, PyJWTError):
                self._last_refresh_failed = True
        if kid in self._keys:
            return self._keys[kid]
        if self._last_refresh_failed and kid in self._retained:
            return self._retained[kid]
        raise HTTPException(
            status_code=503,
            detail="cannot verify identity right now",
            headers={"Retry-After": "30"},
        )


_jwks_caches: dict[str, JwksCache] = {}  # keyed by team domain, one cache per process


def _jwks_cache_for(team: str) -> JwksCache:
    if team not in _jwks_caches:
        _jwks_caches[team] = JwksCache(f"https://{team}.cloudflareaccess.com/cdn-cgi/access/certs")
    return _jwks_caches[team]


async def resolve_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    state = _state(
        request
    )  # from Task 1 — reads request.app.state.rhapto directly, no import of deps.py
    settings = state.settings
    if settings.rhapto_auth_mode != "access":
        expected = settings.rhapto_api_token
        provided = (
            authorization.removeprefix("Bearer ").strip()
            if authorization and authorization.startswith("Bearer ")
            else None
        )
        if not expected or not secrets.compare_digest(provided or "", expected):
            raise HTTPException(
                status_code=401,
                detail="missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Principal(mode="token", subject="token", email=settings.rhapto_user_email.casefold())

    # Cloudflare Access verification. Only the Cf-Access-Jwt-Assertion HEADER is ever consulted --
    # never the CF_Authorization cookie, which the same-origin proxy (Task 2,
    # apps/web/src/app/api/v1/[...path]/route.ts) deliberately drops when forwarding, so a cookie
    # fallback here would be unreachable in this deployment and every request would fail closed.
    assertions = request.headers.getlist("cf-access-jwt-assertion")
    if len(assertions) > 1:
        raise HTTPException(status_code=400, detail="multiple Cf-Access-Jwt-Assertion headers")
    if not assertions:
        raise HTTPException(status_code=401, detail="missing Cf-Access-Jwt-Assertion")
    token = assertions[0]
    try:
        unverified = jwt.get_unverified_header(token)
        # `.get` rather than `unverified["kid"]`: a bare `KeyError` in the except clause below
        # would also catch any unrelated `KeyError` raised anywhere else in this try block
        # (including inside `key_for`) and misreport it as an invalid assertion (M12).
        kid = unverified.get("kid")
        if kid is None:
            raise HTTPException(status_code=401, detail="identity assertion has no kid")
        key = await _jwks_cache_for(settings.rhapto_access_team).key_for(kid)
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=settings.rhapto_access_aud,
            issuer=f"https://{settings.rhapto_access_team}.cloudflareaccess.com",
            leeway=60,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except HTTPException:
        raise
    # `PyJWTError` (not `InvalidTokenError`): `InvalidKeyError`/`PyJWKError` -- raised if a
    # malformed key ever reaches `jwt.decode` -- are direct subclasses of `PyJWTError`, not of
    # `InvalidTokenError`, so the narrower type let that class of failure escape as a 500 (I4).
    except PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid identity assertion") from exc
    email = claims.get("email")
    # A non-string `email` claim (PyJWT does not itself constrain claim types) must be rejected,
    # not silently `str()`-coerced into a garbage identity key (M11).
    if not isinstance(email, str) or not email:
        raise HTTPException(status_code=401, detail="identity assertion has no email claim")
    return Principal(mode="access", subject=str(claims.get("sub", "")), email=email.casefold())
