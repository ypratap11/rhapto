"""A blocked account's queued tailor task must not spend the deployment's key.

The check lives in `tailor_job`, immediately before the budget check and outside the
`trial_claimed` conditional, so an arq re-delivery is refused too. It is not inside the swappable
`ctx["llm_resolver"]`: a gate hidden there is a gate the tests replace.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Any

import pytest
from helpers import default_tailor_script
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import FreeSpend, Task
from rhapto.db.repositories.jobs import create_job
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import get_or_create_user, trial_runs_used
from rhapto.engine.providers.llm import LLMProvider
from rhapto.services import provider_messages
from rhapto.services.secrets import encrypt
from rhapto.services.trial import BLOCKED_MESSAGE
from rhapto.worker import tasks as worker_tasks
from rhapto.worker.tasks import tailor_job

EMAIL = "blocked-worker@example.com"
ENV_KEY = "sk-deployment-only-Zq7W"
OWN_KEY = "sk-the-users-own-key-1234"
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
_SEQ = itertools.count()


@pytest.fixture
def api_settings(tmp_path: Any) -> Any:
    from rhapto.config import Settings

    return Settings(
        _env_file=None,
        anthropic_api_key=ENV_KEY,
        rhapto_api_token="test-token",
        rhapto_user_email=EMAIL,
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
        rhapto_auth_mode="access",
        rhapto_allowed_emails=EMAIL,
        rhapto_access_team="test-team",
        rhapto_access_aud="test-aud",
        rhapto_trial_runs=3,
    )


@pytest.fixture
async def user_id(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session:
        user = await get_or_create_user(session, EMAIL)
        await session.commit()
        return user.id


@pytest.fixture
async def worker_profile(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, demo_profile_dir: Any
) -> None:
    from rhapto.services.profile_sync import import_profile_dir

    async with session_factory() as session:
        await import_profile_dir(session, user_id, demo_profile_dir)
        await session.commit()


async def _block(
    sf: async_sessionmaker[AsyncSession], uid: uuid.UUID, blocked: bool = True
) -> None:
    value = "now()" if blocked else "NULL"
    async with sf() as session:
        await session.execute(
            text(f"UPDATE users SET blocked_at = {value} WHERE id = :u"), {"u": str(uid)}
        )
        await session.commit()


async def _queued(
    sf: async_sessionmaker[AsyncSession], uid: uuid.UUID, claimed: bool = False
) -> str:
    async with sf() as session:
        job = await create_job(
            session,
            uid,
            jd_text=f"{JD} Requisition {next(_SEQ)}.",
            company="ExampleCo",
            title="Program Manager",
        )
        progress: dict[str, Any] = {"request": {"job_id": str(job.id), "mode": "blocks"}}
        if claimed:
            progress["trial_claimed"] = True
        task = Task(user_id=uid, type="tailor_job", status="queued", progress_json=progress)
        session.add(task)
        await session.flush()
        tid = str(task.id)
        await session.commit()
    return tid


async def _task(sf: async_sessionmaker[AsyncSession], tid: str) -> Task:
    async with sf() as session:
        row = await session.get(Task, uuid.UUID(tid))
        assert row is not None
        return row


async def _used(sf: async_sessionmaker[AsyncSession], uid: uuid.UUID) -> int:
    async with sf() as session:
        return await trial_runs_used(session, uid)


async def _spend_rows(sf: async_sessionmaker[AsyncSession]) -> int:
    async with sf() as session:
        return int(await session.scalar(select(func.count()).select_from(FreeSpend)) or 0)


@pytest.mark.usefixtures("worker_profile")
async def test_blocked_user_task_makes_no_model_call(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    fake_llm: Any,
    event_bus: Any,
) -> None:
    await _block(session_factory, user_id)
    tid = await _queued(session_factory, user_id)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    row = await _task(session_factory, tid)
    assert row.status == "failed"
    assert row.error == "This account has been blocked."
    assert row.error == BLOCKED_MESSAGE
    assert fake_llm.calls == []
    assert await _used(session_factory, user_id) == 0
    assert await _spend_rows(session_factory) == 0
    errors = [e for _c, e in event_bus.published if e.get("event") == "error"]
    assert errors and errors[-1]["message"] == BLOCKED_MESSAGE


@pytest.mark.usefixtures("worker_profile")
async def test_redelivery_with_trial_claimed_is_still_refused(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    fake_llm: Any,
) -> None:
    await _block(session_factory, user_id)
    tid = await _queued(session_factory, user_id, claimed=True)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    row = await _task(session_factory, tid)
    assert row.status == "failed" and row.error == BLOCKED_MESSAGE
    assert fake_llm.calls == []


@pytest.mark.usefixtures("worker_profile")
async def test_check_is_not_inside_the_resolver(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    fake_llm: Any,
) -> None:
    async def resolver(session: Any, settings: Any, uid: uuid.UUID) -> LLMProvider:
        return fake_llm  # type: ignore[no-any-return]

    worker_ctx["llm_resolver"] = resolver
    await _block(session_factory, user_id)
    tid = await _queued(session_factory, user_id)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    row = await _task(session_factory, tid)
    assert row.status == "failed" and row.error == BLOCKED_MESSAGE
    assert fake_llm.calls == []


@pytest.mark.usefixtures("worker_profile")
async def test_own_key_user_is_also_refused(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    api_settings: Any,
    fake_llm: Any,
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
    await _block(session_factory, user_id)
    tid = await _queued(session_factory, user_id)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    row = await _task(session_factory, tid)
    assert row.status == "failed" and row.error == BLOCKED_MESSAGE
    assert fake_llm.calls == []


@pytest.mark.usefixtures("worker_profile")
async def test_token_mode_is_not_checked(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    api_settings: Any,
    fake_llm: Any,
) -> None:
    api_settings.rhapto_auth_mode = "token"
    await _block(session_factory, user_id)
    tid = await _queued(session_factory, user_id)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    assert (await _task(session_factory, tid)).status == "succeeded"


@pytest.mark.usefixtures("worker_profile")
async def test_unblocked_user_runs_normally(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    fake_llm: Any,
) -> None:
    await _block(session_factory, user_id)
    await _block(session_factory, user_id, blocked=False)
    tid = await _queued(session_factory, user_id)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, tid)

    assert (await _task(session_factory, tid)).status == "succeeded"
    assert await _used(session_factory, user_id) == 1


def test_moved_constants_are_importable_from_both_places() -> None:
    assert worker_tasks.SHARED_KEY_REJECTED_MESSAGE is provider_messages.SHARED_KEY_REJECTED_MESSAGE
    assert worker_tasks.PROVIDER_DISPLAY_NAMES is provider_messages.PROVIDER_DISPLAY_NAMES
    assert worker_tasks.user_key_message is provider_messages.user_key_message
