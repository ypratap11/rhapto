from __future__ import annotations

import httpx
from fastapi import FastAPI

from rhapto.api.deps import AppState


async def test_principal_email_is_the_owner_email_in_token_mode(client: httpx.AsyncClient) -> None:
    """token mode's Principal carries the bootstrapped owner's email, casefolded."""
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_access_mode_is_a_defined_501_not_a_crash(
    app: FastAPI, anon_client: httpx.AsyncClient
) -> None:
    # Settings is a pydantic BaseSettings with neither frozen=True nor validate_assignment set
    # (verified: Settings.model_config = SettingsConfigDict(env_file=".env", extra="ignore"),
    # config.py:12), so plain attribute assignment on an already-constructed instance works --
    # no object.__setattr__ needed. Both `app`/`api_settings` are function-scoped fixtures
    # (tests/api/conftest.py:109,145), so this mutation never leaks into another test.
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 501
