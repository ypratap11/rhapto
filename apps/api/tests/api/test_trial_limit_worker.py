"""The worker enforces the cap itself, and the claim lands before the money is spent.

The API check is a courtesy: it gives an immediate, legible answer and it is deliberately racy. The
enforcement is here, in `tailor_job`, and these tests reach it by inserting a task row directly --
which is what a task queued before the limit was hit, an arq re-delivery, or any future caller looks
like.

Settings come from `worker_ctx["settings"]` (condition C4). No test in this file touches an
environment variable or calls `get_settings.cache_clear()`.

The starred cases in the architecture (§8 tests 21 and 22) are
`test_the_worker_refuses_a_queued_task_without_spending_anything` and
`test_a_redelivered_task_is_not_charged_twice`.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Any

import pytest
from helpers import bullet, default_tailor_script, demo_extract, demo_resume
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Package, Task
from rhapto.db.repositories.jobs import create_job
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import get_or_create_user, trial_runs_used
from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import LLMProvider, Message, StructuredResult, SystemBlock, T
from rhapto.services.secrets import encrypt
from rhapto.services.trial import trial_limit_message
from rhapto.worker.tasks import SHARED_KEY_REJECTED_MESSAGE, tailor_job

LIMIT = 3
EMAIL = "worker-trial@example.com"
ENV_KEY = "sk-deployment-only-Zq7W"
OWN_KEY = "sk-the-users-own-key-1234"
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
_JOB_SEQUENCE = itertools.count()


@pytest.fixture
def env_llm_key() -> str:
    return ENV_KEY


@pytest.fixture
def api_settings(tmp_path: Any, env_llm_key: str) -> Any:
    from rhapto.config import Settings

    return Settings(
        _env_file=None,
        anthropic_api_key=env_llm_key,
        rhapto_api_token="test-token",
        rhapto_user_email=EMAIL,
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
        rhapto_auth_mode="access",
        rhapto_allowed_emails=EMAIL,
        rhapto_access_team="test-team",
        rhapto_access_aud="test-aud",
        rhapto_trial_runs=LIMIT,
    )


class ExplodingLLM:
    """Raises on its first call, having recorded it: a provider 500 after the money left."""

    model: str | None = None

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        self.calls.append(output_schema.__name__)
        raise RuntimeError("the provider fell over mid-run")


class RejectingLLM:
    """Rejects the key with the provider's own words, the way a real SDK does."""

    model: str | None = None

    def __init__(self, message: str) -> None:
        self.message = message

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        raise ProviderAuthError("openrouter", self.message)


@pytest.fixture
async def trial_user(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with session_factory() as session:
        user = await get_or_create_user(session, EMAIL)
        await session.commit()
        return user.id


async def _set_used(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, used: int
) -> None:
    async with session_factory() as session:
        await session.execute(
            text("UPDATE users SET trial_runs_used = :n WHERE id = :uid"),
            {"n": used, "uid": str(user_id)},
        )
        await session.commit()


async def _used(session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> int:
    async with session_factory() as session:
        return await trial_runs_used(session, user_id)


async def _queued_task(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> str:
    """A `tailor_job` task row and its job, written straight to the database.

    Deliberately bypasses `POST /jobs/{id}/tailor`: the API check is not what is under test here.
    """
    async with session_factory() as session:
        job = await create_job(
            session,
            user_id,
            # `jobs.dedupe_hash` is a hash of the text; every task here needs its own job.
            jd_text=f"{JD} Requisition {next(_JOB_SEQUENCE)}.",
            company="ExampleCo",
            title="Program Manager",
        )
        task = Task(
            user_id=user_id,
            type="tailor_job",
            status="queued",
            progress_json={"request": {"job_id": str(job.id), "mode": "blocks"}},
        )
        session.add(task)
        await session.flush()
        task_id = str(task.id)
        await session.commit()
    return task_id


@pytest.fixture
async def worker_profile(
    session_factory: async_sessionmaker[AsyncSession], trial_user: uuid.UUID, demo_profile_dir: Any
) -> None:
    from rhapto.services.profile_sync import import_profile_dir

    async with session_factory() as session:
        await import_profile_dir(session, trial_user, demo_profile_dir)
        await session.commit()


async def _task(session_factory: async_sessionmaker[AsyncSession], task_id: str) -> Task:
    async with session_factory() as session:
        row = await session.get(Task, uuid.UUID(task_id))
        assert row is not None
        return row


@pytest.mark.usefixtures("worker_profile")
async def test_the_worker_refuses_a_queued_task_without_spending_anything(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    fake_llm: Any,
    event_bus: Any,
) -> None:
    """★ The worker is the enforcement, and it refuses *before* the first model call.

    The call-count assertion is the point. A test that only checked "the task failed" would pass
    against an implementation that spends the money and refuses afterwards -- which is the whole
    failure this change exists to prevent.
    """
    await _set_used(session_factory, trial_user, LIMIT)
    task_id = await _queued_task(session_factory, trial_user)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "failed"
    assert row.error == trial_limit_message(LIMIT), row.error
    assert ":" not in (row.error or "").split(" ")[0], "no TypeName: prefix on a setup error"
    assert fake_llm.calls == [], "the model must not be called at all"
    assert await _used(session_factory, trial_user) == LIMIT, "a refusal consumes nothing"

    published = [event for _channel, event in event_bus.published]
    errors = [e for e in published if e.get("event") == "error"]
    assert errors and errors[-1]["message"] == trial_limit_message(LIMIT)
    for leak in (ENV_KEY, ENV_KEY[-4:], "anthropic", "claude-sonnet-5", "ANTHROPIC_API_KEY"):
        assert leak not in str(published), f"the event bus must not carry {leak!r}"
        assert leak not in (row.error or "")


@pytest.mark.usefixtures("worker_profile")
async def test_a_rejected_shared_key_does_not_relay_the_maintainers_provider_message(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    event_bus: Any,
) -> None:
    """A ProviderAuthError carries the SDK's own words, and those words are the account holder's.

    Right for someone debugging their own key; wrong when the key is the deployment's, because the
    sentence then describes the MAINTAINER's provider account -- its billing state, its quota, its
    balance. The owner of this deployment saw his own OpenRouter credit balance surface exactly this
    way on 2026-09-27. An invited user would have read the same sentence about an account they can
    neither see nor act on.

    `trial_user` has no stored key, so it runs on the deployment's. The provider's text must not
    reach them by any route: not the task row, not the event stream.
    """
    leaky = (
        "402 This request requires more credits. Account acme-corp has $0.13 remaining; "
        "top up at https://openrouter.ai/credits"
    )
    rejecting = RejectingLLM(leaky)

    async def resolver(session: Any, settings: Any, user_id: uuid.UUID) -> LLMProvider:
        return rejecting  # type: ignore[return-value]

    worker_ctx["llm_resolver"] = resolver
    task_id = await _queued_task(session_factory, trial_user)

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "failed"
    assert row.error == SHARED_KEY_REJECTED_MESSAGE, row.error

    published = str([event for _channel, event in event_bus.published])
    for leak in ("402", "credits", "acme-corp", "0.13", "openrouter.ai"):
        assert leak not in (row.error or ""), f"the task row must not carry {leak!r}"
        assert leak not in published, f"the event bus must not carry {leak!r}"


@pytest.mark.usefixtures("worker_profile")
async def test_a_rejected_own_key_still_tells_the_user_what_the_provider_said(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    api_settings: Any,
) -> None:
    """The other half. Without it the fix could be "suppress the provider message" outright, and a
    user debugging their OWN key would lose the only sentence that tells them what is wrong.
    """
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            trial_user,
            provider="anthropic",
            model="claude-sonnet-5",
            api_key_encrypted=encrypt(api_settings, OWN_KEY),
        )
        await session.commit()

    rejecting = RejectingLLM("invalid_api_key: check the key you entered")

    async def resolver(session: Any, settings: Any, user_id: uuid.UUID) -> LLMProvider:
        return rejecting  # type: ignore[return-value]

    worker_ctx["llm_resolver"] = resolver
    task_id = await _queued_task(session_factory, trial_user)

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "failed"
    assert "invalid_api_key" in (row.error or ""), row.error


@pytest.mark.usefixtures("worker_profile")
async def test_a_redelivered_task_is_not_charged_twice(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    fake_llm: Any,
) -> None:
    """★ Retry idempotency.

    arq can re-deliver the same task (job timeout, SIGKILL, a redis re-delivery), and the claim is
    committed before the model call precisely so a worker killed mid-run hands out no free run. Those
    two facts together mean a re-run must re-run the pipeline without claiming again -- otherwise a
    single timeout costs the maintainer two runs of allowance for one run of work. Fails against an
    unconditional claim.
    """
    await _set_used(session_factory, trial_user, LIMIT - 2)
    task_id = await _queued_task(session_factory, trial_user)

    fake_llm.script(*default_tailor_script())
    await tailor_job(worker_ctx, task_id)
    assert (await _task(session_factory, task_id)).status == "succeeded"
    assert await _used(session_factory, trial_user) == LIMIT - 1

    fake_llm.script(*default_tailor_script())
    await tailor_job(worker_ctx, task_id)
    assert await _used(session_factory, trial_user) == LIMIT - 1, "one run of work, one run charged"


@pytest.mark.usefixtures("worker_profile")
async def test_a_run_that_dies_after_the_claim_is_still_charged(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
) -> None:
    """The claim is committed before the first model call, so a mid-run crash is not a free run.

    This is the direction a money guard must err in: the tokens were spent whatever happened next,
    and there is deliberately no refund path -- a refund is a second place the counter can move and
    the first thing an attacker would reach for.
    """
    exploding = ExplodingLLM()

    async def resolver(session: Any, settings: Any, user_id: uuid.UUID) -> LLMProvider:
        return exploding  # type: ignore[return-value]

    worker_ctx["llm_resolver"] = resolver
    task_id = await _queued_task(session_factory, trial_user)

    await tailor_job(worker_ctx, task_id)

    assert (await _task(session_factory, task_id)).status == "failed"
    assert exploding.calls, "the run did reach the provider"
    assert await _used(session_factory, trial_user) == 1


@pytest.mark.usefixtures("worker_profile")
async def test_a_user_with_their_own_key_runs_through_the_worker_uncounted(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    api_settings: Any,
    fake_llm: Any,
) -> None:
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            trial_user,
            provider="anthropic",
            model="claude-sonnet-5",
            api_key_encrypted=encrypt(api_settings, OWN_KEY),
        )
        await session.commit()

    for _ in range(LIMIT + 2):
        task_id = await _queued_task(session_factory, trial_user)
        fake_llm.script(*default_tailor_script())
        await tailor_job(worker_ctx, task_id)
        assert (await _task(session_factory, task_id)).status == "succeeded"
    assert await _used(session_factory, trial_user) == 0


@pytest.mark.usefixtures("worker_profile")
async def test_the_worker_reads_its_limit_from_the_ctx_not_the_settings_singleton(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    api_settings: Any,
    fake_llm: Any,
) -> None:
    """C4, asserted. Raising the cap on the injected `Settings` alone must change what the task does.

    If `tailor_job` read `get_settings()` instead, this test would need to monkeypatch the process
    environment and clear an `lru_cache` -- the documented source of spurious failures in this repo.
    """
    await _set_used(session_factory, trial_user, LIMIT)
    api_settings.rhapto_trial_runs = LIMIT + 1
    task_id = await _queued_task(session_factory, trial_user)
    fake_llm.script(*default_tailor_script())

    await tailor_job(worker_ctx, task_id)

    assert (await _task(session_factory, task_id)).status == "succeeded"
    assert await _used(session_factory, trial_user) == LIMIT + 1


@pytest.mark.usefixtures("worker_profile")
async def test_a_guardrail_blocked_package_still_consumes_a_run(
    worker_ctx: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession],
    trial_user: uuid.UUID,
    fake_llm: Any,
) -> None:
    """AC 6, asserted rather than left to the reader of the code.

    The guardrails run *after* the model does, so a package they refuse is a package the maintainer
    already paid for. The claim sits before `tailor(...)` precisely so this is structural rather than
    a case anyone has to remember -- but a cap that quietly gave a free run back for every blocked
    package would be a cap an unlucky prompt could defeat, so it is checked.

    Nothing here weakens a guardrail: the scripted output invents a metric, the validator catches it,
    and the package persists as `blocked` exactly as it does without the trial.
    """
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet("Cut warehouse cost 25%.", "acme-migration")
    invented_metric = ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")

    task_id = await _queued_task(session_factory, trial_user)
    # Three responses, because a failing validate triggers the pipeline's one repair call and the
    # repair is scripted to make the same mistake -- so the report still fails and the package
    # persists as `blocked`, which is the state under test.
    fake_llm.script(demo_extract(), invented_metric, invented_metric)

    await tailor_job(worker_ctx, task_id)

    row = await _task(session_factory, task_id)
    assert row.status == "succeeded", row.error
    async with session_factory() as session:
        package = await session.get(Package, uuid.UUID(str(row.result_ref)))
    assert package is not None and package.status == "blocked"
    assert {v["rule"] for v in package.guardrail_report_json["violations"]} == {
        "no-unverified-metrics"
    }
    assert len(fake_llm.calls) == 3, "compose, then one repair attempt: all of it billed"
    assert await _used(session_factory, trial_user) == 1, (
        "the money was spent before the guardrail ran"
    )
