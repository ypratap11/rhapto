"""The monthly budget gate's policy and its 409 body, with no database.

`month_free_spend` and `on_deployment_key` are monkeypatched on `services.trial`, so this proves the
decision table; the HTTP and worker wiring is `tests/api/test_free_budget_api.py`.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.errors import install_error_handlers
from rhapto.config import Settings
from rhapto.services import trial as trial_service
from rhapto.services.trial import FREE_RUNS_PAUSED_MESSAGE, FreeRunsPausedError, check_free_budget

USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SENTENCE = (
    "Free runs are paused until the 1st of next month. Add your own provider API key in Settings "
    "to keep going."
)


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        "rhapto_auth_mode": "access",
        "rhapto_llm_provider": "anthropic",
        "anthropic_api_key": "sk-env-deployment-key",
        "rhapto_monthly_free_budget_usd": 1.0,
    }
    base.update(kwargs)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def _session() -> AsyncSession:
    return cast("AsyncSession", object())


def _world(monkeypatch: pytest.MonkeyPatch, *, spend: str, on_key: bool = True) -> None:
    async def spent(session: object) -> Decimal:
        return Decimal(spend)

    async def on_deployment(session: object, settings: object, user_id: object) -> bool:
        return on_key

    monkeypatch.setattr(trial_service, "month_free_spend", spent)
    monkeypatch.setattr(trial_service, "on_deployment_key", on_deployment)


def test_the_message_is_the_exact_copy() -> None:
    assert FREE_RUNS_PAUSED_MESSAGE == SENTENCE
    assert str(FreeRunsPausedError()) == SENTENCE


async def test_spend_at_the_budget_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, spend="1.00")
    with pytest.raises(FreeRunsPausedError):
        await check_free_budget(_session(), _settings(), USER_ID)


async def test_spend_under_the_budget_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, spend="0.99")
    await check_free_budget(_session(), _settings(), USER_ID)


async def test_zero_budget_refuses_every_deployment_key_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _world(monkeypatch, spend="0")
    with pytest.raises(FreeRunsPausedError):
        await check_free_budget(_session(), _settings(rhapto_monthly_free_budget_usd=0), USER_ID)


async def test_negative_budget_disables_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, spend="999")
    await check_free_budget(_session(), _settings(rhapto_monthly_free_budget_usd=-1), USER_ID)


async def test_an_own_key_user_passes_whatever_the_spend(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, spend="999", on_key=False)
    await check_free_budget(_session(), _settings(), USER_ID)


async def test_token_mode_never_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    _world(monkeypatch, spend="999")
    await check_free_budget(_session(), _settings(rhapto_auth_mode="token"), USER_ID)


def test_the_409_body_is_the_sentence_and_leaks_nothing() -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise FreeRunsPausedError()

    res = TestClient(app).get("/boom")
    body = res.json()
    assert res.status_code == 409
    assert body["code"] == "free_runs_paused"
    assert body["detail"] == SENTENCE
    assert set(body) <= {"type", "title", "status", "detail", "code"}
    assert "$" not in res.text and "RHAPTO_" not in res.text
    assert re.findall(r"\d", body["detail"]) == ["1"]
