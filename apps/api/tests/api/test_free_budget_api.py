"""The monthly budget gate over HTTP and in the worker.

Same access-mode setup as `test_free_spend_wiring.py`. Budget 1.00 with one ledger row of 1.00 means
"spent": `month_free_spend() >= budget`. Every refusal is asserted by exact status, `code` and
sentence, so a missing gate fails on the status line (the run would succeed instead).
"""

from __future__ import annotations

import itertools
import re
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import default_tailor_script
from helpers_docx import build_fixture_docx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, resolve_principal
from rhapto.config import Settings
from rhapto.db.models import Task
from rhapto.db.repositories.free_spend import month_free_spend, record_free_spend
from rhapto.db.repositories.jobs import create_job
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import trial_runs_used
from rhapto.engine.import_resume import ImportedBlock, ImportedLocation, ImportedTrack, ResumeImport
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.services.llm import env_llm_config
from rhapto.services.secrets import encrypt
from rhapto.worker.tasks import tailor_job

EMAIL = "test@example.com"
ENV_KEY = "sk-deployment-only-Zq7W"
OWN_KEY = "sk-the-users-own-key-1234"
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
SENTENCE = (
    "Free runs are paused until the 1st of next month. Add your own provider API key in Settings "
    "to keep going."
)
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
        rhapto_monthly_free_budget_usd=1.0,
    )


@pytest.fixture(autouse=True)
def access_mode(app: FastAPI, api_settings: Settings) -> Iterator[None]:
    api_settings.rhapto_auth_mode = "access"
    app.dependency_overrides[resolve_principal] = lambda: Principal(
        mode="access", subject="idp-subject-1", email=EMAIL
    )
    yield
    app.dependency_overrides.clear()


async def _seed_spend(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, usd: str
) -> None:
    async with session_factory() as session:
        await record_free_spend(
            session,
            user_id=user_id,
            model="m",
            input_tokens=1,
            output_tokens=1,
            cache_read_tokens=0,
            cache_creation_tokens=0,
            cost_usd=Decimal(usd),
        )
        await session.commit()


async def _month_spend(session_factory: async_sessionmaker[AsyncSession]) -> Decimal:
    async with session_factory() as session:
        return await month_free_spend(session)


async def _used(session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> int:
    async with session_factory() as session:
        return await trial_runs_used(session, user_id)


async def _free_import_used(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> bool:
    async with session_factory() as session:
        value = await session.scalar(
            text("SELECT free_import_used_at FROM users WHERE id = :uid"), {"uid": str(user_id)}
        )
    return value is not None


async def _job(client: httpx.AsyncClient) -> str:
    jd_text = f"{JD} Requisition {next(_JOB_SEQUENCE)}."
    response = await client.post("/api/v1/jobs", json={"jd_text": jd_text})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


def _assert_paused(response: httpx.Response) -> None:
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "free_runs_paused"
    assert body["detail"] == SENTENCE


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


async def _queued_task(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    progress_extra: dict[str, Any] | None = None,
) -> str:
    async with session_factory() as session:
        job = await create_job(
            session,
            user_id,
            jd_text=f"{JD} Requisition {next(_JOB_SEQUENCE)}.",
            company="ExampleCo",
            title="Program Manager",
        )
        task = Task(
            user_id=user_id,
            type="tailor_job",
            status="queued",
            progress_json={
                "request": {"job_id": str(job.id), "mode": "blocks"},
                **(progress_extra or {}),
            },
        )
        session.add(task)
        await session.flush()
        task_id = str(task.id)
        await session.commit()
    return task_id


async def _task(session_factory: async_sessionmaker[AsyncSession], task_id: str) -> Task:
    async with session_factory() as session:
        row = await session.get(Task, uuid.UUID(task_id))
        assert row is not None
        return row


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_is_refused_with_409_once_the_month_budget_is_spent(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    await _seed_spend(session_factory, user_id, "1.00")
    fake_llm.script(*default_tailor_script())
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    _assert_paused(response)
    assert fake_llm.calls == []


async def test_import_is_refused_once_the_month_budget_is_spent(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    fake = FakeLLMProvider([_proposal()])

    async def _resolve(session: object, settings: object, user_id: object) -> LLMProvider:
        return fake

    monkeypatch.setattr("rhapto.api.routers.profile.resolve_llm", _resolve)
    await _seed_spend(session_factory, user_id, "1.00")
    response = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )
    _assert_paused(response)
    assert fake.calls == []
    assert not await _free_import_used(session_factory, user_id)
    assert await _used(session_factory, user_id) == 0


@pytest.mark.usefixtures("imported_profile")
async def test_worker_refuses_when_budget_ran_out_after_enqueue(
    worker_ctx: dict[str, Any],
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    task_id = await _queued_task(session_factory, user_id)  # enqueued while under budget
    await _seed_spend(session_factory, user_id, "1.00")  # then the money runs out
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "failed"
    assert row.error == SENTENCE, row.error
    assert fake_llm.calls == []
    assert await _used(session_factory, user_id) == 0


@pytest.mark.usefixtures("imported_profile")
async def test_own_key_user_is_not_paused(
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
    await _seed_spend(session_factory, user_id, "5.00")
    fake_llm.script(*default_tailor_script())
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    assert response.status_code in (200, 201, 202), response.text
    assert response.json()["status"] == "succeeded", response.text


@pytest.mark.usefixtures("imported_profile")
async def test_deleting_a_job_does_not_lower_the_month_spend(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job_id = await _job(client)
    fake_llm.script(*default_tailor_script())
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "succeeded", task
    before = await _month_spend(session_factory)
    assert before > 0
    assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 204
    assert await _month_spend(session_factory) == before


@pytest.mark.usefixtures("imported_profile")
async def test_worker_redelivery_still_checks_the_budget(
    worker_ctx: dict[str, Any],
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    task_id = await _queued_task(session_factory, user_id, {"trial_claimed": True})
    await _seed_spend(session_factory, user_id, "1.00")
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "failed"
    assert row.error == SENTENCE, row.error
    assert fake_llm.calls == [], "no model call on a re-delivery past the budget"


@pytest.mark.usefixtures("imported_profile")
async def test_the_pause_leaks_nothing(
    client: httpx.AsyncClient,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    await _seed_spend(session_factory, user_id, "1.00")
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    _assert_paused(response)
    env = env_llm_config(api_settings)
    assert env is not None
    for needle in (env.model, env.provider, ENV_KEY, ENV_KEY[-4:], "RHAPTO_", "$", "anthropic"):
        assert needle not in response.text, f"the body must not carry {needle!r}"
    assert re.findall(r"\d", response.json()["detail"]) == ["1"]


@pytest.mark.usefixtures("imported_profile")
async def test_budget_disabled_never_pauses(
    client: httpx.AsyncClient,
    fake_llm: Any,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    api_settings.rhapto_monthly_free_budget_usd = -1
    await _seed_spend(session_factory, user_id, "9999.00")
    fake_llm.script(*default_tailor_script())
    response = await client.post(f"/api/v1/jobs/{await _job(client)}/tailor", json={})
    assert response.status_code in (200, 201, 202), response.text
    assert response.json()["status"] == "succeeded", response.text
