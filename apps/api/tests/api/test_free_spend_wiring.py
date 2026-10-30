"""The metering wrapper is wired into both places a deployment-key call can be made.

Same access-mode setup as `test_trial_limit_api.py`: boot in token mode, flip `rhapto_auth_mode`, and
override `resolve_principal`. The worker test injects `ctx["llm_resolver"]` (a `ScriptableLLM`), which
is the point of wrapping AFTER the resolver: an injected provider is metered when it applies.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import default_tailor_script
from helpers_docx import build_fixture_docx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, resolve_principal
from rhapto.config import Settings
from rhapto.db.models import FreeSpend
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.engine.import_resume import ImportedBlock, ImportedLocation, ImportedTrack, ResumeImport
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.services.llm import env_llm_config
from rhapto.services.secrets import encrypt

EMAIL = "test@example.com"
ENV_KEY = "sk-deployment-only-Zq7W"
OWN_KEY = "sk-the-users-own-key-1234"
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
_JOB_SEQUENCE = itertools.count()


@pytest.fixture
def api_settings(tmp_path: Any) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key=ENV_KEY,
        rhapto_api_token="test-token",
        rhapto_user_email=EMAIL,
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
        rhapto_allowed_emails=EMAIL,
        rhapto_access_team="test-team",
        rhapto_access_aud="test-aud",
        rhapto_trial_runs=50,
        rhapto_monthly_free_budget_usd=100.0,
    )


@pytest.fixture(autouse=True)
def access_mode(app: FastAPI, api_settings: Settings) -> Iterator[None]:
    api_settings.rhapto_auth_mode = "access"
    app.dependency_overrides[resolve_principal] = lambda: Principal(
        mode="access", subject="idp-subject-1", email=EMAIL
    )
    yield
    app.dependency_overrides.clear()


async def _rows(session_factory: async_sessionmaker[AsyncSession]) -> list[FreeSpend]:
    async with session_factory() as session:
        return list((await session.scalars(select(FreeSpend))).all())


async def _count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(FreeSpend)) or 0)


async def _job(client: httpx.AsyncClient) -> str:
    jd_text = f"{JD} Requisition {next(_JOB_SEQUENCE)}."
    response = await client.post("/api/v1/jobs", json={"jd_text": jd_text})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


async def _tailor(client: httpx.AsyncClient, fake_llm: Any) -> dict[str, Any]:
    fake_llm.script(*default_tailor_script())
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    return dict(response.json())


def _proposal() -> ResumeImport:
    return ResumeImport(
        blocks=[
            ImportedBlock(
                id="acme-lead",
                type="role",
                org="Acme Analytics",
                role="Senior Data Program Manager",
                period="2019-2025",
                content="Led the Snowflake migration for 12 teams.",
            )
        ],
        tracks=[
            ImportedTrack(
                id="tpm",
                name="TPM",
                keywords=[],
                field="program-project-management",
                role="technical-program-manager",
            )
        ],
        location=ImportedLocation(
            location_home="Denver, CO", location_preferred=[], remote_ok=None
        ),
    )


@pytest.mark.usefixtures("imported_profile")
async def test_a_free_tailor_run_writes_ledger_rows(
    client: httpx.AsyncClient,
    fake_llm: Any,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    task = await _tailor(client, fake_llm)
    assert task["status"] == "succeeded", task
    rows = await _rows(session_factory)
    env = env_llm_config(api_settings)
    assert env is not None
    assert len(fake_llm.calls) >= 1
    assert len(rows) == len(fake_llm.calls), "one row per model call made in the run"
    assert {r.model for r in rows} == {env.model}
    assert all(r.cost_usd > 0 for r in rows)


@pytest.mark.usefixtures("imported_profile")
async def test_calls_before_a_failure_are_still_metered(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    good_extract, _ = default_tailor_script()
    fake_llm.script(good_extract, {"not": "a compose output"}, {"not": "a compose output"})
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    assert response.json()["status"] != "succeeded", response.text
    assert await _count(session_factory) >= 1


async def test_a_free_import_writes_ledger_rows(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    fake = FakeLLMProvider([_proposal()])

    async def _resolve(session: object, settings: object, user_id: object) -> LLMProvider:
        return fake

    monkeypatch.setattr("rhapto.api.routers.profile.resolve_llm", _resolve)
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )
    assert res.status_code == 200, res.text
    assert await _count(session_factory) >= 1


@pytest.mark.usefixtures("imported_profile")
async def test_own_key_runs_write_nothing(
    client: httpx.AsyncClient,
    fake_llm: Any,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            user_id,
            provider="anthropic",
            model="claude-sonnet-5",
            api_key_encrypted=encrypt(api_settings, OWN_KEY),
        )
        await session.commit()
    task = await _tailor(client, fake_llm)
    assert task["status"] == "succeeded", task
    assert await _count(session_factory) == 0


@pytest.mark.usefixtures("imported_profile")
async def test_budget_disabled_writes_nothing(
    client: httpx.AsyncClient,
    fake_llm: Any,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    api_settings.rhapto_monthly_free_budget_usd = -1
    task = await _tailor(client, fake_llm)
    assert task["status"] == "succeeded", task
    assert await _count(session_factory) == 0
