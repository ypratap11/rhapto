from __future__ import annotations

import httpx

from rhapto.api.app import create_app
from rhapto.config import Settings


async def test_cors_is_installed_in_token_mode(
    api_settings: Settings, session_factory, storage
) -> None:
    api_settings.rhapto_auth_mode = "token"
    app = create_app(api_settings, session_factory=session_factory, storage=storage)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_is_absent_in_access_mode(
    api_settings: Settings, session_factory, storage
) -> None:
    api_settings.rhapto_auth_mode = "access"
    app = create_app(api_settings, session_factory=session_factory, storage=storage)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers
