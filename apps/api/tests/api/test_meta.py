from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.app import create_app
from rhapto.api.deps import AppState
from rhapto.config import Settings
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.storage import PackageStorage


async def test_health_is_public(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_me_requires_bearer(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401 and body["title"] == "Unauthorized"


async def test_me_rejects_wrong_token(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_me_returns_user(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_openapi_served(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/openapi.json")
    assert response.status_code == 200 and response.json()["info"]["title"] == "Rhapto API"


async def test_unexpected_error_is_problem_json_without_the_exception_text(app: FastAPI) -> None:
    """Any unhandled error must still leave the API as RFC 7807, and must not echo its message."""

    async def boom() -> None:
        raise RuntimeError("kaboom-internal-detail")

    app.add_api_route("/api/v1/_boom", boom, methods=["GET"])
    # raise_app_exceptions=False: Starlette's ServerErrorMiddleware re-raises after responding.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as anon:
        response = await anon.get("/api/v1/_boom")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Internal Server Error" and body["status"] == 500
    assert body["detail"] == "unexpected server error"
    assert "kaboom-internal-detail" not in response.text


async def test_integrity_error_is_409_problem_json(app: FastAPI, client: httpx.AsyncClient) -> None:
    async def conflict() -> None:
        raise IntegrityError("INSERT INTO packages ...", {}, Exception("duplicate key"))

    app.add_api_route("/api/v1/_conflict", conflict, methods=["GET"])
    response = await client.get("/api/v1/_conflict")
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert (
        body["title"] == "Conflict" and body["detail"] == "the change conflicts with existing data"
    )
    assert "duplicate key" not in response.text


async def test_me_is_503_when_the_user_is_not_bootstrapped_yet(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """A valid token before the lifespan finished is a readiness problem, not an auth problem."""
    state: AppState = app.state.rhapto
    bootstrapped, state.user_id = state.user_id, None
    try:
        response = await client.get("/api/v1/me")
    finally:
        state.user_id = bootstrapped
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "server not ready"


async def test_lifespan_closes_the_broker_clients(
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    storage: PackageStorage,
    fake_fetch: Callable[[str], Awaitable[str]],
) -> None:
    class ClosingEnqueuer:
        closed = False

        async def enqueue(self, task: str, **kwargs: Any) -> None: ...

        async def close(self) -> None:
            self.closed = True

    class ClosingBus(InMemoryEventBus):
        closed = False

        async def close(self) -> None:
            self.closed = True

    enqueuer, bus = ClosingEnqueuer(), ClosingBus()
    application = create_app(
        api_settings,
        session_factory=session_factory,
        enqueuer=enqueuer,
        event_bus=bus,
        storage=storage,
        fetch_text=fake_fetch,
    )
    async with LifespanManager(application):
        pass
    assert enqueuer.closed and bus.closed
