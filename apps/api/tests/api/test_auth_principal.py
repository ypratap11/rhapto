from __future__ import annotations

import httpx
from fastapi import FastAPI

from rhapto.api.deps import AppState


async def test_principal_email_is_the_owner_email_in_token_mode(client: httpx.AsyncClient) -> None:
    """token mode's Principal carries the bootstrapped owner's email, casefolded."""
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_access_mode_without_an_assertion_is_a_defined_401_not_a_crash(
    app: FastAPI, anon_client: httpx.AsyncClient
) -> None:
    """Task 3 replaces the 501 stub with real Cloudflare Access verification (`test_access_mode.py`
    covers the verified path end to end); a request with no Cf-Access-Jwt-Assertion header at all
    is the simplest access-mode case reachable from this module's fixtures, and must fail closed
    with a defined 401 rather than a 501 stub or an unhandled exception.

    Settings is a pydantic BaseSettings with neither frozen=True nor validate_assignment set
    (verified: Settings.model_config = SettingsConfigDict(env_file=".env", extra="ignore"),
    config.py:12), so plain attribute assignment on an already-constructed instance works --
    no object.__setattr__ needed. Both `app`/`api_settings` are function-scoped fixtures
    (tests/api/conftest.py:109,145), so this mutation never leaks into another test.
    """
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 401
