from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rhapto.api.admin_guard import AdminRoute
from rhapto.api.admin_schemas import AdminSessionOut

router = APIRouter(prefix="/admin", route_class=AdminRoute, include_in_schema=False)


@router.get("/session", response_model=AdminSessionOut)
async def admin_session() -> AdminSessionOut:
    """Reached only when the guard has proven the caller an admin."""
    return AdminSessionOut(ok=True)


# Real admin routes (Tasks 11 and 12) must be registered ABOVE this call: Starlette takes the first
# full match, so the catch-all has to come last.
_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]


def _register_catch_all(r: APIRouter) -> None:
    # Every method, so none answers 405 + `Allow` (which would reveal the area to anyone); and the
    # bare `/admin` too, since `/{rest:path}` needs the slash and Starlette would redirect (307)
    # before any guard ran.
    @r.api_route("", methods=_ALL_METHODS, include_in_schema=False)
    @r.api_route("/{rest:path}", methods=_ALL_METHODS, include_in_schema=False)
    async def admin_unknown(rest: str = "") -> None:
        raise HTTPException(status_code=404)


_register_catch_all(router)
