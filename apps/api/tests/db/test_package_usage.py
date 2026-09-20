from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Package, User
from rhapto.db.repositories import jobs as jobs_repo


async def _job(session: AsyncSession, user: User, external_id: str):
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id=external_id,
        company="ExampleCo",
        title="Technical Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash=f"hash-{external_id}",
        repost_of=None,
    )
    await session.flush()
    return job


async def test_usage_columns_round_trip(session: AsyncSession, user: User) -> None:
    job = await _job(session, user, "usage-1")
    package = Package(
        user_id=user.id,
        job_id=job.id,
        track_id="t",
        version=1,
        status="draft",
        resume_json={},
        cover_note="",
        change_log="",
        guardrail_report_json={},
        jd_extract_json={},
        input_tokens=1200,
        output_tokens=340,
        cache_read_tokens=50,
        cache_creation_tokens=20,
        llm_model="claude-sonnet-5",
    )
    session.add(package)
    await session.flush()
    assert package.input_tokens == 1200
    assert package.output_tokens == 340
    assert package.cache_read_tokens == 50
    assert package.cache_creation_tokens == 20
    assert package.llm_model == "claude-sonnet-5"


async def test_usage_columns_default_to_zero_and_none(session: AsyncSession, user: User) -> None:
    """Rows written before this column existed (or that never specify usage) read as 0/None."""
    job = await _job(session, user, "usage-2")
    package = Package(
        user_id=user.id,
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
    await session.flush()
    assert package.input_tokens == 0
    assert package.output_tokens == 0
    assert package.cache_read_tokens == 0
    assert package.cache_creation_tokens == 0
    assert package.llm_model is None
