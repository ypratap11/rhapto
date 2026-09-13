"""The Settings LLM endpoints: what is configured, storing a key, and probing a provider.

Every test here runs with an environment that has no provider key (the `env_llm_key` override), so
what the endpoints report comes from the stored row alone.
"""

from __future__ import annotations

import base64
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories.llm_settings import get_llm_settings
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.types import EngineError

KEY = "sk-test-1234"
URL = "/api/v1/settings/llm"


@pytest.fixture
def env_llm_key(request: pytest.FixtureRequest) -> str:
    """Nothing in the environment unless a test parametrizes this indirectly."""
    return str(getattr(request, "param", ""))


class FactorySpy:
    """Stands in for `build_llm`: records the call and returns a scripted adapter (or raises)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.error: Exception | None = None
        self.llm = FakeLLMProvider([{"ok": True}])

    def __call__(self, provider: str, model: str, api_key: str) -> LLMProvider:
        self.calls.append((provider, model, api_key))
        if self.error is not None:
            raise self.error
        return self.llm


@pytest.fixture
def llm_factory() -> FactorySpy:
    return FactorySpy()


async def _put(client: httpx.AsyncClient, **body: Any) -> httpx.Response:
    return await client.put(URL, json=body)


async def test_get_reports_nothing_configured_and_lists_the_providers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "none" and body["key_set"] is False
    assert body["provider"] is None and body["model"] is None and body["key_hint"] is None
    assert [p["id"] for p in body["providers"]] == ["anthropic", "openai", "gemini"]
    openai_info = body["providers"][1]
    assert openai_info["label"] == "OpenAI" and openai_info["default"] == "gpt-5"
    assert "gpt-5-mini" in openai_info["models"]


@pytest.mark.parametrize("env_llm_key", ["sk-test-env"], indirect=True)
async def test_get_falls_back_to_the_environment(client: httpx.AsyncClient) -> None:
    body = (await client.get(URL)).json()
    assert body["source"] == "env" and body["key_set"] is True
    assert body["provider"] == "anthropic" and body["model"] == "claude-sonnet-5"
    assert body["key_hint"] == "…-env"


async def test_put_stores_the_key_encrypted_and_never_echoes_it(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    response = await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "openai" and body["model"] == "gpt-5"
    assert body["source"] == "settings" and body["key_set"] is True
    assert body["key_hint"] == "…1234"
    assert "sk-test" not in response.text

    async with session_factory() as session:
        row = await get_llm_settings(session, user_id)
    assert row is not None and row.provider == "openai" and row.model == "gpt-5"
    assert KEY not in row.api_key_encrypted

    stored = (await client.get(URL)).json()
    assert stored["source"] == "settings" and stored["key_hint"] == "…1234"


async def test_put_without_a_key_keeps_the_stored_one(client: httpx.AsyncClient) -> None:
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    again = await _put(client, provider="openai", model="gpt-5-mini")
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["model"] == "gpt-5-mini" and body["key_set"] is True
    assert body["key_hint"] == "…1234"


async def test_put_switching_provider_without_a_key_is_422(client: httpx.AsyncClient) -> None:
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    switched = await _put(client, provider="gemini", model="gemini-2.5-pro")
    assert switched.status_code == 422
    assert "Google Gemini" in switched.json()["detail"]
    unchanged = (await client.get(URL)).json()
    assert unchanged["provider"] == "openai" and unchanged["model"] == "gpt-5"


async def test_put_rejects_an_unknown_provider(client: httpx.AsyncClient) -> None:
    response = await _put(client, provider="nope", model="x", api_key=KEY)
    assert response.status_code == 422 and "nope" in response.json()["detail"]


async def test_delete_removes_the_row(client: httpx.AsyncClient) -> None:
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    assert (await client.delete(URL)).status_code == 204
    assert (await client.get(URL)).json()["source"] == "none"
    # Deleting again is still a 204: the end state the caller asked for is what matters.
    assert (await client.delete(URL)).status_code == 204


async def test_me_reports_whether_an_llm_is_configured(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).json()["llm_configured"] is False
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    assert (await client.get("/api/v1/me")).json()["llm_configured"] is True


async def test_post_test_pings_the_provider_through_the_injected_factory(
    client: httpx.AsyncClient, llm_factory: FactorySpy
) -> None:
    response = await client.post(
        f"{URL}/test", json={"provider": "openai", "model": "gpt-5", "api_key": KEY}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "model": "gpt-5", "error": None}
    assert llm_factory.calls == [("openai", "gpt-5", KEY)]
    assert llm_factory.llm.calls[0].messages[0].content == "ping"
    assert "sk-test" not in response.text


async def test_post_test_uses_the_stored_key_when_the_body_has_none(
    client: httpx.AsyncClient, llm_factory: FactorySpy
) -> None:
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    response = await client.post(f"{URL}/test", json={"provider": "openai", "model": "gpt-5"})
    assert response.status_code == 200 and response.json()["ok"] is True
    assert llm_factory.calls == [("openai", "gpt-5", KEY)]


async def test_post_test_reports_a_rejected_key_as_not_ok(
    client: httpx.AsyncClient, llm_factory: FactorySpy
) -> None:
    llm_factory.error = ProviderAuthError("openai", "bad key")
    response = await client.post(
        f"{URL}/test", json={"provider": "openai", "model": "gpt-5", "api_key": KEY}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": False, "model": None, "error": "bad key"}


async def test_post_test_reports_an_engine_error_as_not_ok(
    client: httpx.AsyncClient, llm_factory: FactorySpy
) -> None:
    llm_factory.error = EngineError("x" * 400)
    body = (
        await client.post(
            f"{URL}/test", json={"provider": "openai", "model": "gpt-5", "api_key": KEY}
        )
    ).json()
    assert body["ok"] is False and len(body["error"]) == 300


async def test_post_test_without_any_key_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{URL}/test", json={"provider": "gemini", "model": ""})
    assert response.status_code == 422 and "Google Gemini" in response.json()["detail"]


async def test_settings_endpoints_require_the_bearer_token(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get(URL)).status_code == 401
    assert (await anon_client.put(URL, json={"provider": "openai", "model": ""})).status_code == 401
    assert (await anon_client.delete(URL)).status_code == 401


async def test_an_unreadable_stored_key_is_a_409_not_a_500(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    """Rotating the server secret leaves stored keys undecryptable; that is a setup conflict the
    user can fix by re-entering the key, not a server fault."""
    await _put(client, provider="openai", model="gpt-5", api_key=KEY)
    other_key = base64.urlsafe_b64encode(b"x" * 32).decode()
    app.state.rhapto.settings.rhapto_secret_key = other_key
    response = await client.get(URL)
    assert response.status_code == 409
    assert response.json()["code"] == "llm_key_unreadable"
    assert "Settings" in response.json()["detail"]
    assert (await client.get("/api/v1/me")).json()["llm_configured"] is False
