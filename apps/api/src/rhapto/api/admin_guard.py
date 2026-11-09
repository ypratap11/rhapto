"""Owner-only guard for the admin area.

`AdminRoute` runs `enforce_admin` before FastAPI parses the request body, so a non-admin cannot
tell an admin route from an unknown path (a router-level dependency would answer malformed JSON
with 422). The guard touches no database: the admin's identity is the verified Cloudflare Access
assertion, so a missing or blocked `users` row cannot lock the owner out.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import HTTPException, Request, Response
from fastapi.routing import APIRoute

from rhapto.api.auth import is_allowed_email, resolve_principal

_SAFE_METHODS = frozenset({"GET", "HEAD"})
NO_STORE = "no-store"


async def enforce_admin(request: Request) -> str:
    """Return the admin's email, or raise 404 (not admin, or identity cannot be verified) or 403 (Origin).

    Order matters: nothing about the admin area is revealed before the caller is proven an admin.
    """
    settings = request.app.state.rhapto.settings
    if settings.rhapto_auth_mode != "access":
        raise HTTPException(status_code=404)
    try:
        principal = await resolve_principal(request, request.headers.get("authorization"))
    except HTTPException:
        # Every principal failure, a 503 from key lookup included, is the unknown-path 404: a forged
        # token with an unknown `kid` would otherwise reach a 503 only on admin paths. Never forward
        # the underlying detail.
        raise HTTPException(status_code=404) from None
    # Empty domains argument makes domain matching impossible; same casefold comparison.
    if not is_allowed_email(principal.email, settings.rhapto_admin_emails, ""):
        raise HTTPException(status_code=404)
    if request.method not in _SAFE_METHODS:
        origins = request.headers.getlist("origin")
        if len(origins) != 1 or origins[0] != settings.rhapto_web_origin.rstrip("/"):
            raise HTTPException(status_code=403)
    request.state.admin_email = principal.email
    return principal.email


class AdminRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            # Only a response that reaches a proven admin is no-store. The non-admin 404 must stay
            # byte-identical to an unknown path, headers included, so it is rendered bare.
            try:
                await enforce_admin(request)
            except HTTPException as exc:
                response = await _render(request, exc)
                if exc.status_code != 404:
                    response.headers["Cache-Control"] = NO_STORE
                return response
            try:
                response = await original(request)
            except Exception as exc:
                response = await _render(request, exc)
            response.headers["Cache-Control"] = NO_STORE
            return response

        return guarded


async def _render(request: Request, exc: Exception) -> Response:
    """Render `exc` through the app's own handlers (404 body identical to an unknown path, 422,
    500 ...)."""
    handler = next(
        (
            h
            for cls in type(exc).__mro__
            if (h := request.app.exception_handlers.get(cls)) is not None
        ),
        None,
    )
    if handler is None:
        raise exc
    result = handler(request, exc)
    response: Response = await result if inspect.isawaitable(result) else result
    return response
