"""The trial cap over HTTP: three runs on the deployment's key, then a refusal that says what to do.

Access mode without a Cloudflare Access JWT: the app boots in token mode (so the lifespan bootstraps
the single `users` row and `state.user_id`), then `access_mode` flips `rhapto_auth_mode` and overrides
`resolve_principal` with an already-verified `Principal`. JWT verification itself is
`test_access_mode.py`'s subject; what matters here is that `current_user` takes the access branch and
that `Settings.rhapto_auth_mode` reads "access" for both the app and the in-process worker -- the same
`Settings` instance reaches the worker through `worker_ctx["settings"]` (condition C4), so no test here
touches an environment variable or `get_settings.cache_clear()`.

The starred cases in the architecture (§8 tests 14, 18 and 19) are
`test_the_refusal_leaks_nothing_about_the_deployments_provider`,
`test_deleting_a_job_does_not_give_the_allowance_back` and
`test_a_human_edit_never_consumes_a_run`.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import default_tailor_script
from helpers_docx import build_fixture_docx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, resolve_principal
from rhapto.config import Settings
from rhapto.db.models import Task
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import trial_runs_used
from rhapto.engine.import_resume import ImportedBlock, ImportedLocation, ImportedTrack, ResumeImport
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.services.secrets import encrypt

LIMIT = 3
EMAIL = "test@example.com"
#: Distinctive on purpose: every assertion that the refusal leaks nothing greps the response and the
#: log for this string and for its last four characters, and a needle like "test" would match the
#: fixture email instead of proving anything.
ENV_KEY = "sk-deployment-only-Zq7W"
OWN_KEY = "sk-the-users-own-key-1234"
JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


@pytest.fixture
def env_llm_key(request: pytest.FixtureRequest) -> str:
    """The deployment's key. Parametrize indirectly with "" for the no-key-anywhere paths."""
    return str(getattr(request, "param", ENV_KEY))


@pytest.fixture
def api_settings(tmp_path: Any, env_llm_key: str) -> Settings:
    """Token mode at construction; `access_mode` flips it once the app has started.

    The access-mode lifespan branch refuses to boot unless a matching `users` row already exists
    (`api/app.py`), and it is the token-mode branch that creates that row -- so booting in token mode
    and flipping afterwards is the short way to an access-mode app with a user, and it exercises
    exactly the two settings the cap reads.
    """
    return Settings(
        _env_file=None,
        anthropic_api_key=env_llm_key,
        rhapto_api_token="test-token",
        rhapto_user_email=EMAIL,
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
        rhapto_allowed_emails=EMAIL,
        rhapto_access_team="test-team",
        rhapto_access_aud="test-aud",
        rhapto_trial_runs=LIMIT,
    )


@pytest.fixture(autouse=True)
def access_mode(app: FastAPI, api_settings: Settings) -> Iterator[None]:
    api_settings.rhapto_auth_mode = "access"
    app.dependency_overrides[resolve_principal] = lambda: Principal(
        mode="access", subject="idp-subject-1", email=EMAIL
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def stored_own_key(
    session_factory: async_sessionmaker[AsyncSession], api_settings: Settings, user_id: uuid.UUID
) -> None:
    """A key of the user's own, so nothing they do is billed to the deployment."""
    async with session_factory() as session:
        await upsert_llm_settings(
            session,
            user_id,
            provider="anthropic",
            model="claude-sonnet-5",
            api_key_encrypted=encrypt(api_settings, OWN_KEY),
        )
        await session.commit()


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


async def _task_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return int(await session.scalar(select(func.count()).select_from(Task)) or 0)


async def _tailor(client: httpx.AsyncClient, fake_llm: Any, job_id: str) -> httpx.Response:
    fake_llm.script(*default_tailor_script())
    return await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})


#: `POST /jobs` dedupes on a hash of `jd_text` and answers 409 for a repeat, so every job a test
#: creates needs its own description.
_JOB_SEQUENCE = itertools.count()


async def _job(client: httpx.AsyncClient) -> str:
    jd_text = f"{JD} Requisition {next(_JOB_SEQUENCE)}."
    response = await client.post("/api/v1/jobs", json={"jd_text": jd_text})
    assert response.status_code in (200, 201), response.text
    return str(response.json()["id"])


async def _spend(client: httpx.AsyncClient, fake_llm: Any, runs: int) -> list[str]:
    """`runs` successful tailor runs, each on its own job."""
    ids: list[str] = []
    for _ in range(runs):
        job_id = await _job(client)
        task = (await _tailor(client, fake_llm, job_id)).json()
        assert task["status"] == "succeeded", task
        ids.append(job_id)
    return ids


# --- the cap itself ---


@pytest.mark.usefixtures("imported_profile")
async def test_three_runs_succeed_and_the_fourth_is_refused_before_anything_is_enqueued(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """AC 1: the refusal lands before any model call, and leaves no task row behind to fail later."""
    await _spend(client, fake_llm, LIMIT)
    assert await _used(session_factory, user_id) == LIMIT

    job_id = await _job(client)
    tasks_before = await _task_count(session_factory)
    calls_before = len(fake_llm.calls)
    refused = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})

    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["code"] == "trial_limit_reached"
    assert body["used"] == LIMIT and body["limit"] == LIMIT
    assert "Settings" in body["detail"] and str(LIMIT) in body["detail"]
    assert await _task_count(session_factory) == tasks_before, "no task row for a refused run"
    assert len(fake_llm.calls) == calls_before, "the fourth run must not reach the model at all"
    assert await _used(session_factory, user_id) == LIMIT, "a refusal consumes nothing"


@pytest.mark.usefixtures("imported_profile")
async def test_the_refusal_leaks_nothing_about_the_deployments_provider(
    client: httpx.AsyncClient,
    fake_llm: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """★ AC 2's second half, proved rather than asserted.

    A test that only checked `code == "trial_limit_reached"` would pass while the body named the
    provider, quoted the model, or carried the last four characters of the maintainer's live key --
    which is exactly what `GET /settings/llm` was doing on the adjacent screen (condition C2). The
    log is checked too: `logger.warning("%s", exc)` on a setup error is how this class of leak
    happens, and `services/trial.py` deliberately logs nothing at all.
    """
    await _spend(client, fake_llm, LIMIT)
    job_id = await _job(client)

    with caplog.at_level(logging.DEBUG):
        refused = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert refused.status_code == 409

    for leak in (
        ENV_KEY,
        ENV_KEY[-4:],
        "anthropic",
        "Anthropic",
        "claude-sonnet-5",
        "ANTHROPIC_API_KEY",
        "env",
    ):
        assert leak not in refused.text, f"the refusal must not name {leak!r}: {refused.text}"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for leak in (ENV_KEY, ENV_KEY[-4:], "anthropic", "claude-sonnet-5", "ANTHROPIC_API_KEY"):
        assert leak not in logged, f"the log must not name {leak!r}: {logged}"


@pytest.mark.usefixtures("imported_profile", "stored_own_key")
async def test_a_user_with_their_own_key_is_never_capped(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """AC 3, and proof the counter is not a global run counter: past the limit, still zero."""
    await _spend(client, fake_llm, LIMIT + 3)
    assert await _used(session_factory, user_id) == 0


@pytest.mark.parametrize("env_llm_key", [""], indirect=True)
@pytest.mark.usefixtures("imported_profile")
async def test_no_key_anywhere_is_still_llm_not_configured(client: httpx.AsyncClient) -> None:
    """Ordering (architecture §5.1): the trial refusal is unreachable on a deployment that has no key
    of its own to protect, and a user with no key anywhere keeps the answer they already got."""
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "llm_not_configured"


@pytest.mark.usefixtures("imported_profile")
async def test_token_mode_is_never_capped(
    client: httpx.AsyncClient,
    fake_llm: Any,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """A self-hosted `.env`-only install: its one user is the operator and the env key is theirs.

    Without this exemption a default of `RHAPTO_TRIAL_RUNS=3` would silently cap every self-hoster
    and every e2e stack.
    """
    api_settings.rhapto_auth_mode = "token"
    await _spend(client, fake_llm, LIMIT + 2)
    assert await _used(session_factory, user_id) == 0


# --- the two mechanisms the functional spec proposed, and why they are not used ---


@pytest.mark.usefixtures("imported_profile")
async def test_deleting_a_job_does_not_give_the_allowance_back(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """★ The deletion bypass, and the regression guard that nobody reintroduces the spec's mechanism.

    `Package.job_id` is `ON DELETE CASCADE`, so `DELETE /jobs/{id}` deletes that job's packages.
    Counting `packages` rows therefore makes the cap resettable by an ordinary product action -- one
    HTTP call, no privileges, unbounded: tailor, delete, repeat forever. This test fails against that
    mechanism and passes against a counter the user cannot reach.
    """
    job_ids = await _spend(client, fake_llm, LIMIT)
    assert await _used(session_factory, user_id) == LIMIT

    for job_id in job_ids:
        assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 204
    assert (await client.get("/api/v1/jobs")).json() == []
    assert await _used(session_factory, user_id) == LIMIT, "the money was already spent"

    fresh = await _job(client)
    refused = await client.post(f"/api/v1/jobs/{fresh}/tailor", json={})
    assert refused.status_code == 409 and refused.json()["code"] == "trial_limit_reached"


@pytest.mark.usefixtures("imported_profile")
async def test_a_human_edit_never_consumes_a_run(
    client: httpx.AsyncClient,
    fake_llm: Any,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """★ The human-edit false charge, and the second regression guard against the spec's mechanism.

    `PATCH /packages/{id}` is the review-queue edit path. It makes no model call, yet it writes a new
    `packages` row through `persist_package`, and `package_row_to_model` copies the parent's
    `llm_model` (the `model_copy` resets `llm_calls` but not `model`). Under "a run is a row with
    llm_model IS NOT NULL", a user who tailored once and edited twice would be told they had spent
    all three paid runs -- charging someone for nothing.
    """
    job_id = await _job(client)
    fake_llm.script(*default_tailor_script())
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "succeeded", task
    package_id = str(task["result_ref"])
    assert await _used(session_factory, user_id) == 1

    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["sections"][0]["entries"][0]["bullets"][0]["text"] = (
        "Led cross-functional delivery of the customer data platform across 4 teams, on time."
    )
    for expected_version in (2, 3):
        edited = await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})
        assert edited.status_code == 201, edited.text
        assert edited.json()["version"] == expected_version and edited.json()["llm_calls"] == 0
        package_id = str(edited.json()["id"])

    assert await _used(session_factory, user_id) == 1, "an edit is not a run on anyone's key"
    # And the allowance really is still there: two more runs, no refusal.
    await _spend(client, fake_llm, 2)
    assert await _used(session_factory, user_id) == LIMIT


# --- the third money-spending path the functional spec missed ---


def _import_proposal() -> ResumeImport:
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


@pytest.fixture
def import_llm(monkeypatch: pytest.MonkeyPatch) -> FakeLLMProvider:
    """The adapter `POST /profile/import-resume` resolves, scripted and counted.

    The endpoint calls `resolve_llm` directly rather than through the worker's injectable resolver,
    and the default settings would otherwise build a real Anthropic client.
    """
    fake = FakeLLMProvider([_import_proposal() for _ in range(LIMIT + 2)])

    async def _resolve(session: object, settings: object, user_id: object) -> LLMProvider:
        return fake

    monkeypatch.setattr("rhapto.api.routers.profile.resolve_llm", _resolve)
    return fake


async def _import_resume(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", build_fixture_docx())}
    )


async def test_first_import_is_free_then_counted(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Spec 3.2: the first import costs the tester nothing; every later one is one run."""
    assert (await _import_resume(client)).status_code == 200
    assert len(import_llm.calls) == 1
    assert await _used(session_factory, user_id) == 0
    assert await _free_import_used(session_factory, user_id)

    assert (await _import_resume(client)).status_code == 200
    assert await _used(session_factory, user_id) == 1  # the second import consumes one run


async def test_importing_past_the_limit_after_the_free_one_is_refused_without_a_model_call(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    for _ in range(LIMIT + 1):
        assert (await _import_resume(client)).status_code == 200
    assert await _used(session_factory, user_id) == LIMIT
    calls_before = len(import_llm.calls)

    refused = await _import_resume(client)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "trial_limit_reached"
    assert len(import_llm.calls) == calls_before, "the refusal must precede the model call"
    assert ENV_KEY not in refused.text and ENV_KEY[-4:] not in refused.text


async def test_two_concurrent_imports_give_exactly_one_free(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """SMOKE TEST ONLY. A bare `gather` does not force the interleaving, so it passes for a
    SELECT-then-UPDATE implementation whenever one request finishes first (this repo said so in
    `tests/db/test_trial_claim.py`). The discriminating test is
    `test_two_concurrent_free_import_claims_give_exactly_one` below the claim tests. What this one
    proves is that the route wires the claim in at all: two imports, one free, one counted."""
    first, second = await asyncio.gather(_import_resume(client), _import_resume(client))
    assert first.status_code == 200 and second.status_code == 200
    assert await _used(session_factory, user_id) == 1
    assert await _free_import_used(session_factory, user_id)


async def test_zero_cap_refuses_the_first_import_and_leaves_the_column_alone(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """RHAPTO_TRIAL_RUNS=0 means this instance offers no free runs: the free import must not
    bypass it."""
    api_settings.rhapto_trial_runs = 0
    refused = await _import_resume(client)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "trial_limit_reached"
    assert len(import_llm.calls) == 0
    assert not await _free_import_used(session_factory, user_id)


async def test_cap_disabled_import_makes_no_claim(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    api_settings.rhapto_trial_runs = -1  # an operator disabled the cap
    assert (await _import_resume(client)).status_code == 200
    assert await _used(session_factory, user_id) == 0
    assert not await _free_import_used(session_factory, user_id)


@pytest.mark.usefixtures("stored_own_key")
async def test_own_key_import_leaves_the_free_import_unspent(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Checking the flag before `trial_limit_for` would burn an own-key user's free import on a
    call the deployment never paid for."""
    assert (await _import_resume(client)).status_code == 200
    assert not await _free_import_used(session_factory, user_id)
    assert await _used(session_factory, user_id) == 0


@pytest.mark.usefixtures("stored_own_key")
async def test_importing_a_resume_on_your_own_key_is_not_counted(
    client: httpx.AsyncClient,
    import_llm: FakeLLMProvider,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    assert (await _import_resume(client)).status_code == 200
    assert await _used(session_factory, user_id) == 0


# --- the probe stays open, on purpose ---


async def test_the_key_probe_is_not_gated_by_the_trial(
    app: FastAPI,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Ruled on rather than left implicit (architecture §1.4): gating the probe would refuse the
    check of the very key someone is adding in order to escape the cap. Bounded by size, not count."""
    async with session_factory() as session:
        await session.execute(
            text("UPDATE users SET trial_runs_used = :n WHERE id = :uid"),
            {"n": LIMIT, "uid": str(user_id)},
        )
        await session.commit()

    probed: list[tuple[str, str, str]] = []

    def factory(provider: str, model: str, api_key: str) -> LLMProvider:
        probed.append((provider, model, api_key))
        return FakeLLMProvider([{"ok": True}])

    app.state.rhapto.llm_factory = factory
    response = await client.post(
        "/api/v1/settings/llm/test",
        json={"provider": "anthropic", "model": "claude-sonnet-5", "api_key": "sk-brand-new-key"},
    )
    assert response.status_code == 200 and response.json()["ok"] is True
    assert probed == [("anthropic", "claude-sonnet-5", "sk-brand-new-key")]
    assert await _used(session_factory, user_id) == LIMIT
