"""`MeteredLLM` writes one ledger row per billed call. No database: the session is a recorder."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.config import Settings
from rhapto.db.models import FreeSpend
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import (
    MalformedOutputError,
    Message,
    StructuredResult,
    SystemBlock,
    TokenUsage,
)
from rhapto.services import trial as trial_service
from rhapto.services.free_spend import MeteredLLM, meter_if_free
from rhapto.services.pricing import MODEL_RATES, conservative_cost, estimate_cost

USER = uuid.uuid4()


class Answer(BaseModel):
    text: str = "ok"


class _Session:
    def __init__(self, ledger: _Ledger) -> None:
        self._ledger = ledger
        self._pending: list[FreeSpend] = []

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def add(self, row: FreeSpend) -> None:
        self._pending.append(row)

    async def commit(self) -> None:
        if self._ledger.fail:
            raise RuntimeError("database is down")
        self._ledger.rows.extend(self._pending)


class _Ledger:
    """A stand-in for `async_sessionmaker`: every committed `add` lands in `rows`."""

    def __init__(self, *, fail: bool = False) -> None:
        self.rows: list[FreeSpend] = []
        self.fail = fail

    def __call__(self) -> _Session:
        return _Session(self)


class _Raising:
    model: str | None = None

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete_structured(self, **_: Any) -> StructuredResult[Any]:
        raise self._exc


async def _call(llm: Any) -> StructuredResult[Answer]:
    result: StructuredResult[Answer] = await llm.complete_structured(
        system=[SystemBlock(text="s")],
        messages=[Message(role="user", content="go")],
        output_schema=Answer,
    )
    return result


def _metered(inner: Any, ledger: Any, model: str = "claude-opus-5") -> MeteredLLM:
    return MeteredLLM(inner, model=model, user_id=USER, session_factory=ledger)


async def test_each_returned_call_writes_one_row() -> None:
    ledger = _Ledger()
    llm = _metered(FakeLLMProvider(responses=[{"text": "a"}, {"text": "b"}]), ledger)
    await _call(llm)
    await _call(llm)
    assert len(ledger.rows) == 2
    expected = estimate_cost("claude-opus-5", TokenUsage(input_tokens=10, output_tokens=5))
    for row in ledger.rows:
        assert (row.input_tokens, row.output_tokens) == (10, 5)
        assert row.user_id == USER and row.model == "claude-opus-5"
        assert row.cost_usd == expected


async def test_unpriced_model_is_recorded_at_the_highest_rate() -> None:
    ledger = _Ledger()

    class _Big:
        model = "mystery-1"

        async def complete_structured(self, **_: Any) -> StructuredResult[Any]:
            return StructuredResult(value=Answer(), usage=TokenUsage(input_tokens=1_000_000))

    await _call(_metered(_Big(), ledger, model="mystery-1"))
    assert ledger.rows[0].cost_usd == max(r.input_per_million for r in MODEL_RATES.values())
    assert ledger.rows[0].cost_usd > 0


def test_conservative_cost_prices_output_and_cache_at_the_worst_rates() -> None:
    usage = TokenUsage(
        output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )
    top_in = max(r.input_per_million for r in MODEL_RATES.values())
    top_out = max(r.output_per_million for r in MODEL_RATES.values())
    expected = top_out + top_in * Decimal("0.1") + top_in * Decimal("1.25")
    assert conservative_cost(None, usage) == expected
    assert conservative_cost("claude-opus-5", usage) == estimate_cost("claude-opus-5", usage)


async def test_a_raising_call_writes_nothing() -> None:
    ledger = _Ledger()
    boom = RuntimeError("provider fell over")
    with pytest.raises(RuntimeError) as excinfo:
        await _call(_metered(_Raising(boom), ledger))
    assert excinfo.value is boom
    assert ledger.rows == []


async def test_a_malformed_call_is_metered_then_reraised() -> None:
    ledger = _Ledger()
    bad = MalformedOutputError("bad shape", usage=TokenUsage(input_tokens=1000))
    with pytest.raises(MalformedOutputError) as excinfo:
        await _call(_metered(_Raising(bad), ledger))
    assert excinfo.value is bad
    assert [r.input_tokens for r in ledger.rows] == [1000]


async def test_a_malformed_call_without_usage_writes_nothing() -> None:
    ledger = _Ledger()
    with pytest.raises(MalformedOutputError):
        await _call(_metered(_Raising(MalformedOutputError("no response")), ledger))
    assert ledger.rows == []


async def test_a_failing_ledger_write_is_logged_and_the_result_still_returned(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ledger = _Ledger(fail=True)
    with caplog.at_level(logging.ERROR):
        result = await _call(_metered(FakeLLMProvider(responses=[{"text": "kept"}]), ledger))
    assert result.value.text == "kept"
    assert str(USER) in caplog.text
    assert "RuntimeError" in caplog.text
    assert "database is down" not in caplog.text


def test_metered_llm_exposes_the_model() -> None:
    llm = _metered(FakeLLMProvider(responses=[]), _Ledger(), model="claude-opus-5")
    assert llm.model == "claude-opus-5"


async def _meter_for(monkeypatch: pytest.MonkeyPatch, email: str) -> Any:
    """`meter_if_free` for a keyless account on a hosted instance whose operator is the owner.

    The session is a fake: monkeypatching `trial_service.email_of` (and the stored-key lookup) is
    what keeps both the admin check and `on_deployment_key` from touching a database.
    """

    async def stored(session: object, settings: object, user_id: object) -> None:
        return None

    async def email_of(session: object, user_id: object) -> str:
        return email

    monkeypatch.setattr(trial_service, "stored_llm_config", stored)
    monkeypatch.setattr(trial_service, "email_of", email_of)
    settings = Settings(
        _env_file=None,
        rhapto_auth_mode="access",
        rhapto_llm_provider="anthropic",
        anthropic_api_key="sk-env-deployment-key",
        rhapto_monthly_free_budget_usd=1.0,
        rhapto_admin_emails="owner@example.com",
    )
    inner = FakeLLMProvider(responses=[{"text": "a"}])
    wrapped = await meter_if_free(
        inner, cast("AsyncSession", object()), settings, USER, cast("Any", _Ledger())
    )
    return inner, wrapped


async def test_u11_an_admins_calls_are_not_metered(monkeypatch: pytest.MonkeyPatch) -> None:
    inner, wrapped = await _meter_for(monkeypatch, "owner@example.com")
    assert wrapped is inner


async def test_u11_a_non_admins_calls_are_metered(monkeypatch: pytest.MonkeyPatch) -> None:
    inner, wrapped = await _meter_for(monkeypatch, "tester@example.com")
    assert isinstance(wrapped, MeteredLLM)
