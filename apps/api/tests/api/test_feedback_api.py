"""POST /api/v1/feedback: insert-only, self-only, validated, rate-limited, never logged.

Fictional testers and invented text only.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import rhapto
from rhapto.api.routers import feedback as feedback_router
from rhapto.db.models import FeedbackRow, Job, Package
from rhapto.db.repositories import feedback as feedback_repo
from rhapto.db.repositories.users import get_or_create_user

URL = "/api/v1/feedback"
FULL_SURVEY: dict[str, Any] = {
    "session": {"task": "find_jobs", "finished": "partly", "minutes": "10_30"},
    "getting_started": {"ease": 4, "stuck": "Could not find the settings page."},
    "profile": {"ease": 3, "missing_or_confusing": "What is a block?"},
    "finding_jobs": {"match_quality": 2, "bad_match_example": "A nursing job showed up."},
    "review": {
        "resume_quality": 4,
        "flagged": "yes",
        "flag_verdict": "right",
        "would_have_noticed": "not_sure",
        "wrongly_blocked": "Nothing.",
    },
    "downloads": {"looked_right": "yes", "problems": "None."},
    "overall": {
        "would_use": "maybe",
        "would_pay_19": "no",
        "pay_why": "Too much for me.",
        "fix_first": "Make the dashboard clearer.",
        "quote_ok": True,
    },
}


def survey(answers: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"form": "survey", "answers": FULL_SURVEY if answers is None else answers}


def quick(area: str = "dashboard", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "form": "quick",
        "page_area": area,
        "answers": {"kind": "bug", "rating": 2, "text": "The button did nothing."},
    }
    body.update(extra)
    return body


async def _rows(session_factory: async_sessionmaker[AsyncSession]) -> list[FeedbackRow]:
    async with session_factory() as session:
        return list((await session.scalars(select(FeedbackRow))).all())


# ---- success ---------------------------------------------------------------------------------


async def test_full_survey_is_stored(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    response = await client.post(URL, json=survey())
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"id", "created_at"}
    (row,) = await _rows(session_factory)
    assert row.user_id == user_id
    assert row.form == "survey" and row.page_area is None
    assert row.schema_version == 1
    assert row.job_id is None and row.package_id is None
    assert row.answers["overall"]["quote_ok"] is True
    assert row.answers["getting_started"]["ease"] == 4


async def test_one_section_survey_is_accepted(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json=survey({"overall": {"would_use": "yes"}}))
    assert response.status_code == 201, response.text


async def test_quick_with_area_is_stored(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    response = await client.post(URL, json=quick("review"))
    assert response.status_code == 201, response.text
    (row,) = await _rows(session_factory)
    assert row.form == "quick" and row.page_area == "review"
    assert row.answers == {"kind": "bug", "rating": 2, "text": "The button did nothing."}


async def test_two_posts_make_two_rows(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    first = await client.post(URL, json=quick())
    second = await client.post(URL, json=quick())
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert len(await _rows(session_factory)) == 2


# ---- validation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"form": "survey", "answers": {}}, id="empty-survey"),
        pytest.param({"form": "survey", "answers": {"overall": {}}}, id="only-default-quote-ok"),
        pytest.param(
            {"form": "survey", "answers": {"overall": {"quote_ok": True}}}, id="consent-alone"
        ),
        pytest.param(
            {"form": "quick", "page_area": "jobs", "answers": FULL_SURVEY}, id="quick-with-survey"
        ),
        pytest.param(
            {"form": "survey", "answers": {"kind": "bug", "text": "x"}}, id="survey-with-quick"
        ),
        pytest.param({"form": "quick", "answers": {"kind": "bug"}}, id="quick-without-area"),
        pytest.param(
            {"form": "survey", "page_area": "jobs", "answers": FULL_SURVEY}, id="survey-with-area"
        ),
        pytest.param(quick("nowhere"), id="unknown-area"),
        pytest.param(
            {"form": "quick", "page_area": "jobs", "answers": {"kind": "rant"}}, id="unknown-kind"
        ),
        pytest.param(
            {"form": "quick", "page_area": "jobs", "answers": {"kind": "bug", "text": "x" * 2001}},
            id="2001-chars",
        ),
        pytest.param({**survey(), "user_id": str(uuid.uuid4())}, id="user-id-in-body"),
        pytest.param({**survey(), "app_version": "9.9.9"}, id="app-version-in-body"),
        pytest.param(
            {**survey({"overall": {"would_use": "yes"}}), "job_id": str(uuid.uuid4())},
            id="survey-with-job-id",
        ),
        pytest.param({"form": "other", "answers": {}}, id="unknown-form"),
    ],
)
async def test_invalid_bodies_are_422(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    body: dict[str, Any],
) -> None:
    response = await client.post(URL, json=body)
    assert response.status_code == 422, response.text
    assert await _rows(session_factory) == []


async def test_2000_chars_is_accepted(client: httpx.AsyncClient) -> None:
    body = quick()
    body["answers"]["text"] = "x" * 2000
    assert (await client.post(URL, json=body)).status_code == 201


async def test_nul_in_text_is_422_not_500_and_is_not_echoed(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    sentinel = f"SENTINEL-{uuid.uuid4()}"
    body = quick()
    body["answers"]["text"] = f"{sentinel}\x00tail"
    response = await client.post(URL, json=body)
    assert response.status_code == 422, response.text
    assert sentinel not in response.text
    assert await _rows(session_factory) == []

    survey_body = survey({"overall": {"fix_first": f"{sentinel}\x00"}})
    response = await client.post(URL, json=survey_body)
    assert response.status_code == 422, response.text
    assert sentinel not in response.text


# ---- auth and rate limit ---------------------------------------------------------------------


async def test_unauthenticated_is_401(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.post(URL, json=quick())).status_code == 401


async def test_51st_in_24h_is_429(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        for _ in range(feedback_router.FEEDBACK_DAILY_LIMIT):
            await feedback_repo.insert(
                session,
                user_id=user_id,
                form="quick",
                page_area="jobs",
                schema_version=1,
                answers={"kind": "idea"},
                app_version="0.1.0",
                job_id=None,
                package_id=None,
            )
        await session.commit()
    assert feedback_router.FEEDBACK_DAILY_LIMIT == 50
    response = await client.post(URL, json=quick())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "3600"
    assert response.json()["code"] == "feedback_rate_limited"
    assert len(await _rows(session_factory)) == 50


async def test_another_users_rows_do_not_count_against_the_limit(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "tester-b@example.com")
        for _ in range(50):
            await feedback_repo.insert(
                session,
                user_id=other.id,
                form="survey",
                page_area=None,
                schema_version=1,
                answers={},
                app_version="0.1.0",
                job_id=None,
                package_id=None,
            )
        await session.commit()
    assert (await client.post(URL, json=quick())).status_code == 201


# ---- tenancy ---------------------------------------------------------------------------------


async def _job_and_package(session: AsyncSession, user_id: uuid.UUID) -> tuple[Job, Package]:
    job = Job(
        user_id=user_id,
        source="manual",
        jd_text="Fictional role at Example Co.",
        dedupe_hash=uuid.uuid4().hex,
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    package = Package(
        user_id=user_id,
        job_id=job.id,
        track_id="t",
        version=1,
        status="draft",
        resume_json={},
        cover_note="",
        change_log="",
    )
    session.add(package)
    await session.commit()
    return job, package


async def test_own_context_ids_are_kept(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        job, package = await _job_and_package(session, user_id)
    body = quick("review", job_id=str(job.id), package_id=str(package.id))
    assert (await client.post(URL, json=body)).status_code == 201
    (row,) = await _rows(session_factory)
    assert row.user_id == user_id
    assert (row.job_id, row.package_id) == (job.id, package.id)


async def test_another_users_context_ids_are_stored_null(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "tester-b@example.com")
        await session.commit()
        job, package = await _job_and_package(session, other.id)
    body = quick("review", job_id=str(job.id), package_id=str(package.id))
    assert (await client.post(URL, json=body)).status_code == 201
    (row,) = await _rows(session_factory)
    assert row.user_id == user_id
    assert row.job_id is None and row.package_id is None


# ---- no read path ----------------------------------------------------------------------------


def test_exactly_one_feedback_route_and_it_is_the_post(app: FastAPI) -> None:
    """Must fail if anyone adds a list/get/delete route for feedback."""
    found = [
        (route.path, sorted(route.methods))
        for route in app.routes
        if isinstance(route, APIRoute) and "feedback" in route.path
    ]
    assert found == [("/api/v1/feedback", ["POST"])]


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
async def test_other_methods_are_405(client: httpx.AsyncClient, method: str) -> None:
    response = await client.request(method, URL)
    assert response.status_code == 405


# ---- version ---------------------------------------------------------------------------------


async def test_app_version_is_server_stamped(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await client.post(URL, json=quick())
    (row,) = await _rows(session_factory)
    assert row.app_version == rhapto.__version__


async def test_app_version_carries_the_build_id(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    app: FastAPI,
) -> None:
    app.state.rhapto.settings.rhapto_build_id = "abc123"
    await client.post(URL, json=quick())
    (row,) = await _rows(session_factory)
    assert row.app_version == f"{rhapto.__version__}+abc123"


# ---- logging privacy -------------------------------------------------------------------------


async def test_integrity_error_logs_no_tester_text(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Postgres' DETAIL ("Failing row contains (...)") carries the row, so `str(exc)` and any
    traceback would leak the sentinel. Asserts on `caplog.text` (which includes formatted
    tracebacks), NOT `record.getMessage()` (which never sees `exc_info`)."""
    sentinel = f"SENTINEL-{uuid.uuid4()}"
    real_insert = feedback_repo.insert

    async def bad_insert(session: AsyncSession, **kwargs: Any) -> FeedbackRow:
        # A survey carrying a page_area violates ck_feedback_area_iff_quick.
        kwargs.update(form="survey", page_area="dashboard")
        return await real_insert(session, **kwargs)

    monkeypatch.setattr(feedback_router.feedback_repo, "insert", bad_insert)
    body = quick()
    body["answers"]["text"] = sentinel
    caplog.set_level(logging.DEBUG)
    response = await client.post(URL, json=body)

    assert response.status_code == 409
    assert sentinel not in response.text
    assert sentinel not in caplog.text
    assert "ck_feedback_area_iff_quick" in caplog.text
    assert "sqlstate=23514" in caplog.text
