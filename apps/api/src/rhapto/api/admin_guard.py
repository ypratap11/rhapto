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
    """Return the admin's email, or raise 404 (not admin), 503 (cannot verify) or 403 (Origin).

    Order matters: nothing about the admin area is revealed before the caller is proven an admin.
    """
    settings = request.app.state.rhapto.settings
    if settings.rhapto_auth_mode != "access":
        raise HTTPException(status_code=404)
    try:
        principal = await resolve_principal(request, request.headers.get("authorization"))
    except HTTPException as exc:
        # 503 ("cannot verify identity right now") stays diagnosable; every other failure is
        # indistinguishable from an unknown path. Never forward the underlying detail.
        if exc.status_code == 503:
            raise HTTPException(status_code=503, headers=exc.headers) from None
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
            try:
                await enforce_admin(request)
                response = await original(request)
            except Exception as exc:
                # Render through the app's own handlers (404 body identical to an unknown path,
                # 422, 500 ...) so that every admin response, whatever its status, gets no-store.
                handler = next(
                    (
                        h
                        for cls in type(exc).__mro__
                        if (h := request.app.exception_handlers.get(cls)) is not None
                    ),
                    None,
                )
                if handler is None:
                    raise
                result = handler(request, exc)
                response = await result if inspect.isawaitable(result) else result
            response.headers["Cache-Control"] = NO_STORE
            return response

        return guarded
