"""GET /api/v1/settings/usage: per-user token/cost totals, priced per model then summed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Package
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories.users import get_or_create_user

URL = "/api/v1/settings/usage"


async def _job(session: AsyncSession, user_id: uuid.UUID, external_id: str):
    return await jobs_repo.create_discovered_job(
        session,
        user_id,
        source="themuse",
        external_id=external_id,
        company="ExampleCo",
        title="Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash=f"hash-{external_id}",
        repost_of=None,
    )


def _package(
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    version: int = 1,
    llm_calls: int = 2,
    input_tokens: int = 0,
    output_tokens: int = 0,
    llm_model: str | None = None,
    created_at: datetime | None = None,
) -> Package:
    return Package(
        user_id=user_id,
        job_id=job_id,
        track_id="t",
        version=version,
        status="draft",
        resume_json={},
        cover_note="",
        change_log="",
        guardrail_report_json={},
        jd_extract_json={},
        llm_calls=llm_calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_model=llm_model,
        created_at=created_at or datetime.now(UTC),
    )


async def test_empty_account_reports_zeroes(client: httpx.AsyncClient) -> None:
    body = (await client.get(URL)).json()
    assert body["totals"]["calls"] == 0
    assert body["totals"]["cost_usd"] is None
    assert body["recent"] == []


async def test_cost_is_priced_per_model_then_summed(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Two packages on DIFFERENT models: the total must be the sum of each model's own price, not
    (sum of tokens) * a single rate -- that would misreport as soon as a user switches models."""
    async with session_factory() as session:
        job = await _job(session, user_id, "usage-1")
        session.add(
            _package(
                user_id,
                job.id,
                version=1,
                llm_calls=2,
                input_tokens=1_000_000,
                output_tokens=0,
                llm_model="claude-opus-5",
            )
        )
        session.add(
            _package(
                user_id,
                job.id,
                version=2,
                llm_calls=3,
                input_tokens=1_000_000,
                output_tokens=0,
                llm_model="claude-sonnet-5",
            )
        )
        await session.commit()

    body = (await client.get(URL)).json()
    totals = body["totals"]
    assert totals["calls"] == 5
    assert totals["input_tokens"] == 2_000_000
    # claude-opus-5 $5/1M-in + claude-sonnet-5 $2/1M-in, priced separately then added.
    assert totals["cost_usd"] == pytest.approx(5.00 + 2.00)
    assert totals["unpriced_calls"] == 0


async def test_null_model_rows_contribute_tokens_but_no_cost(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        job = await _job(session, user_id, "usage-2")
        session.add(
            _package(user_id, job.id, version=1, llm_calls=2, input_tokens=500, llm_model=None)
        )
        await session.commit()

    body = (await client.get(URL)).json()
    totals = body["totals"]
    assert totals["calls"] == 2
    assert totals["input_tokens"] == 500
    assert totals["cost_usd"] is None
    assert totals["unpriced_calls"] == 2


async def test_last_30_days_excludes_older_packages(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        job = await _job(session, user_id, "usage-3")
        old = datetime.now(UTC) - timedelta(days=40)
        session.add(
            _package(
                user_id,
                job.id,
                version=1,
                llm_calls=1,
                input_tokens=100,
                llm_model="claude-sonnet-5",
                created_at=old,
            )
        )
        recent = datetime.now(UTC) - timedelta(days=1)
        session.add(
            _package(
                user_id,
                job.id,
                version=2,
                llm_calls=1,
                input_tokens=200,
                llm_model="claude-sonnet-5",
                created_at=recent,
            )
        )
        await session.commit()

    body = (await client.get(URL)).json()
    assert body["totals"]["calls"] == 2
    assert body["last_30_days"]["calls"] == 1
    assert body["last_30_days"]["input_tokens"] == 200


async def test_recent_lists_newest_packages_with_job_info(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        job = await _job(session, user_id, "usage-4")
        pkg = _package(
            user_id,
            job.id,
            version=1,
            llm_calls=2,
            input_tokens=10,
            output_tokens=5,
            llm_model="claude-sonnet-5",
        )
        session.add(pkg)
        await session.commit()
        await session.refresh(pkg)
        pkg_id = pkg.id

    body = (await client.get(URL)).json()
    assert len(body["recent"]) == 1
    row = body["recent"][0]
    assert row["package_id"] == str(pkg_id)
    assert row["job_id"] == str(job.id)
    assert row["company"] == "ExampleCo"
    assert row["job_title"] == "Program Manager"
    assert row["model"] == "claude-sonnet-5"
    assert row["calls"] == 2
    assert row["input_tokens"] == 10 and row["output_tokens"] == 5
    assert row["cost_usd"] == pytest.approx((10 * 2.00 + 5 * 10.00) / 1_000_000)


async def test_usage_is_scoped_to_the_current_user(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "other-usage@example.com")
        await session.commit()
        other_job = await _job(session, other.id, "usage-other")
        session.add(
            _package(
                other.id,
                other_job.id,
                version=1,
                llm_calls=9,
                input_tokens=999,
                llm_model="claude-opus-5",
            )
        )
        mine_job = await _job(session, user_id, "usage-mine")
        session.add(
            _package(user_id, mine_job.id, version=1, llm_calls=1, input_tokens=1, llm_model=None)
        )
        await session.commit()

    body = (await client.get(URL)).json()
    assert body["totals"]["calls"] == 1
    assert body["totals"]["input_tokens"] == 1
    assert len(body["recent"]) == 1
