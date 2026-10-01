"""QA adversarial cases for POST /api/v1/feedback (DB-backed: run in CI only).

A malicious or careless tester: forged identity, borrowed context ids, boundary text, odd Unicode,
malformed bodies. Fictional data only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.routers import feedback as feedback_router
from rhapto.db.models import FeedbackRow, Job, Package
from rhapto.db.repositories import feedback as feedback_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.feedback import TEXT_MAX

URL = "/api/v1/feedback"

TEXT_FIELDS = [
    ("session", "task_other"),
    ("getting_started", "stuck"),
    ("profile", "missing_or_confusing"),
    ("finding_jobs", "bad_match_example"),
    ("review", "wrongly_blocked"),
    ("downloads", "problems"),
    ("overall", "pay_why"),
    ("overall", "fix_first"),
]
ALL_SECTIONS = (
    "session",
    "getting_started",
    "profile",
    "finding_jobs",
    "review",
    "downloads",
    "overall",
)


def _quick(**answers: Any) -> dict[str, Any]:
    return {"form": "quick", "page_area": "jobs", "answers": {"kind": "idea", **answers}}


def _quick_with(answers: dict[str, Any]) -> dict[str, Any]:
    return {"form": "quick", "page_area": "jobs", "answers": answers}


async def _rows(factory: async_sessionmaker[AsyncSession]) -> list[FeedbackRow]:
    async with factory() as session:
        return list((await session.scalars(select(FeedbackRow))).all())


async def _insert(session: AsyncSession, user_id: uuid.UUID, n: int) -> None:
    for _ in range(n):
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


@pytest.mark.parametrize(("section", "field"), TEXT_FIELDS)
async def test_every_survey_text_field_accepts_2000_and_refuses_2001(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    section: str,
    field: str,
) -> None:
    ok = await client.post(
        URL, json={"form": "survey", "answers": {section: {field: "y" * TEXT_MAX}}}
    )
    assert ok.status_code == 201, ok.text
    over = await client.post(
        URL, json={"form": "survey", "answers": {section: {field: "y" * (TEXT_MAX + 1)}}}
    )
    assert over.status_code == 422
    assert "y" * 50 not in over.text
    assert len(await _rows(session_factory)) == 1


async def test_quick_text_boundary_is_exactly_2000(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    assert (await client.post(URL, json=_quick(text="z" * 2000))).status_code == 201
    assert (await client.post(URL, json=_quick(text="z" * 2001))).status_code == 422
    assert len(await _rows(session_factory)) == 1


async def test_whitespace_padding_is_trimmed_before_the_limit(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    body = _quick(text="   " + "z" * 2000 + "   ")
    assert (await client.post(URL, json=body)).status_code == 201
    (row,) = await _rows(session_factory)
    assert row.answers["text"] == "z" * 2000


async def test_whitespace_only_text_is_dropped_not_stored(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    assert (await client.post(URL, json=_quick(text="  \n\t "))).status_code == 201
    (row,) = await _rows(session_factory)
    assert "text" not in row.answers


@pytest.mark.parametrize(
    "value",
    [
        "\U0001f600\U0001f680 emoji",
        "שלום مرحبا",
        "‮evil‬",
        "line one\nline two\n\n\tindented",
        "café é ‍ zero-width",
    ],
)
async def test_unicode_and_newline_text_round_trips_exactly(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    value: str,
) -> None:
    assert (await client.post(URL, json=_quick(text=value))).status_code == 201
    (row,) = await _rows(session_factory)
    assert row.answers["text"] == value.strip()


async def test_2000_astral_characters_fit_the_limit(client: httpx.AsyncClient) -> None:
    assert (await client.post(URL, json=_quick(text="\U0001f600" * 2000))).status_code == 201


@pytest.mark.parametrize("extra", [{"schema_version": 7}, {"schema_version": 1}, {"id": "x"}])
async def test_client_cannot_set_schema_version_or_server_fields(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    extra: dict[str, Any],
) -> None:
    response = await client.post(URL, json={**_quick(), **extra})
    assert response.status_code == 422
    assert await _rows(session_factory) == []


async def test_forged_identity_in_query_or_headers_is_ignored(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "tester-b@example.com")
        await session.commit()
        other_id = other.id
    response = await client.post(
        f"{URL}?user_id={other_id}",
        json=_quick(),
        headers={"X-User-Id": str(other_id), "X-Forwarded-User": str(other_id)},
    )
    assert response.status_code == 201
    (row,) = await _rows(session_factory)
    assert row.user_id == user_id
    assert row.user_id != other_id


async def test_response_does_not_echo_answers_or_context(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json=_quick(text="private words"))
    assert set(response.json()) == {"id", "created_at"}


async def _job_pkg(session: AsyncSession, user_id: uuid.UUID) -> tuple[Job, Package]:
    job = Job(
        user_id=user_id,
        source="manual",
        jd_text="Fictional role.",
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
        guardrail_report_json={},
        jd_extract_json={},
    )
    session.add(package)
    await session.commit()
    return job, package


async def test_mixed_own_job_and_foreign_package_keeps_only_the_own_one(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "tester-b@example.com")
        await session.commit()
        mine, _ = await _job_pkg(session, user_id)
        _, theirs = await _job_pkg(session, other.id)
    body = {**_quick(), "page_area": "review", "job_id": str(mine.id), "package_id": str(theirs.id)}
    assert (await client.post(URL, json=body)).status_code == 201
    (row,) = await _rows(session_factory)
    assert row.job_id == mine.id
    assert row.package_id is None


@pytest.mark.parametrize("bad", ["not-a-uuid", "", "1", 5, "../../etc/passwd"])
async def test_malformed_context_ids_are_422(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    bad: Any,
) -> None:
    for key in ("job_id", "package_id"):
        assert (await client.post(URL, json={**_quick(), key: bad})).status_code == 422
    assert await _rows(session_factory) == []


HOSTILE: list[Any] = [
    pytest.param(
        {"form": "survey", "answers": {"session": {}, "overall": {}}}, id="empty-sections"
    ),
    pytest.param(
        {"form": "survey", "answers": {name: {} for name in ALL_SECTIONS}}, id="all-seven-empty"
    ),
    pytest.param(
        {"form": "survey", "answers": {"profile": {"missing_or_confusing": "  "}}}, id="blank-text"
    ),
    pytest.param(
        {"form": "quick", "page_area": "Dashboard", "answers": {"kind": "bug"}}, id="area-case"
    ),
    pytest.param({"form": "quick", "page_area": "", "answers": {"kind": "bug"}}, id="area-empty"),
    pytest.param(_quick_with({"kind": "bug", "rating": 0}), id="rating-0"),
    pytest.param(_quick_with({"kind": "bug", "rating": 6}), id="rating-6"),
    pytest.param(_quick_with({"kind": "bug", "rating": 4.5}), id="rating-float"),
    pytest.param({"form": "survey", "answers": {"overall": {"would_use": "YES"}}}, id="enum-case"),
    pytest.param(
        {"form": "survey", "answers": {"overall": {"fix_first": "x", "extra": 1}}},
        id="unknown-field",
    ),
    pytest.param({"form": "survey", "answers": {"nonsense": {"a": 1}}}, id="unknown-section"),
    pytest.param(_quick_with({"kind": "bug", "text": "a\x07b"}), id="bell"),
    pytest.param({"form": "quick", "page_area": "jobs", "answers": None}, id="null-answers"),
    pytest.param({"form": "quick", "page_area": "jobs"}, id="missing-answers"),
    pytest.param({}, id="empty-object"),
]


@pytest.mark.parametrize("body", HOSTILE)
async def test_hostile_bodies_are_422_and_store_nothing(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    body: dict[str, Any],
) -> None:
    response = await client.post(URL, json=body)
    assert response.status_code == 422, response.text
    assert await _rows(session_factory) == []


@pytest.mark.parametrize(
    ("content", "ctype"),
    [
        (b"[1,2,3]", "application/json"),
        (b"null", "application/json"),
        (b"{not json", "application/json"),
        (b"form=quick", "application/x-www-form-urlencoded"),
        (b"", "application/json"),
    ],
)
async def test_non_object_or_non_json_bodies_are_4xx_never_5xx(
    client: httpx.AsyncClient, content: bytes, ctype: str
) -> None:
    response = await client.post(URL, content=content, headers={"Content-Type": ctype})
    assert 400 <= response.status_code < 500, response.text


async def test_the_50th_row_is_accepted_and_the_51st_is_refused(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    limit = feedback_router.FEEDBACK_DAILY_LIMIT
    async with session_factory() as session:
        await _insert(session, user_id, limit - 1)
    assert (await client.post(URL, json=_quick())).status_code == 201
    assert (await client.post(URL, json=_quick())).status_code == 429
    assert len(await _rows(session_factory)) == limit


async def test_a_refused_survey_leaves_no_partial_row(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        await _insert(session, user_id, feedback_router.FEEDBACK_DAILY_LIMIT)
    response = await client.post(
        URL, json={"form": "survey", "answers": {"overall": {"would_use": "yes"}}}
    )
    assert response.status_code == 429
    assert len(await _rows(session_factory)) == feedback_router.FEEDBACK_DAILY_LIMIT


async def test_rows_older_than_24h_do_not_count(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        await _insert(session, user_id, feedback_router.FEEDBACK_DAILY_LIMIT)
        await session.execute(text("UPDATE feedback SET created_at = now() - interval '25 hours'"))
        await session.commit()
    assert (await client.post(URL, json=_quick())).status_code == 201


async def test_a_deleted_user_leaves_no_rows_for_the_owner_report(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        gone = await get_or_create_user(session, "tester-gone@example.com")
        await session.commit()
        await _insert(session, gone.id, 2)
        await session.execute(text("DELETE FROM users WHERE id = :i"), {"i": gone.id})
        await session.commit()
    async with session_factory() as session:
        assert await feedback_repo.all_with_email(session, None) == []
