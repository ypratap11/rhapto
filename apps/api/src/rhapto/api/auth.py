from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import Header, HTTPException, Request

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


async def resolve_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    state = _state(request)
    mode = state.settings.rhapto_auth_mode
    if mode == "access":
        # Task 3 replaces this branch with real Cloudflare Access JWT verification, the JWKS
        # cache, and the allowlist check. Unreachable today: the default is "token" and no
        # deployment can select "access" before Task 3 ships.
        raise HTTPException(status_code=501, detail="access mode is not yet supported")
    expected = state.settings.rhapto_api_token
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
    return Principal(
        mode="token", subject="token", email=state.settings.rhapto_user_email.casefold()
    )
