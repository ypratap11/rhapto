from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application, Job, JobScore, Package, ResumeBlock, User, WatchlistEntry
from rhapto.db.repositories import dashboard as dashboard_repo
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories.users import get_or_create_user


async def test_get_or_create_user_is_idempotent(session: AsyncSession) -> None:
    a = await get_or_create_user(session, "x@example.com")
    b = await get_or_create_user(session, "x@example.com")
    assert a.id == b.id


async def test_block_round_trip_with_arrays_and_vector(session: AsyncSession, user: User) -> None:
    block = ResumeBlock(
        user_id=user.id,
        block_id="acme-migration",
        type="achievement",
        content="Owned it.",
        verified=True,
        tags=["migration", "cost"],
        exclude_when=["agency"],
        embedding=[0.1] * 384,
    )
    session.add(block)
    await session.commit()
    loaded = await session.scalar(
        select(ResumeBlock).where(ResumeBlock.block_id == "acme-migration")
    )
    assert (
        loaded is not None
        and loaded.tags == ["migration", "cost"]
        and loaded.exclude_when == ["agency"]
    )
    assert loaded.verified is True and len(list(loaded.embedding)) == 384
    assert loaded.created_at is not None


async def test_job_defaults(session: AsyncSession, user: User) -> None:
    job = Job(user_id=user.id, jd_text="text", dedupe_hash="abc", discovered_at=datetime.now(UTC))
    session.add(job)
    await session.commit()
    assert job.source == "manual" and job.company is None


async def test_truncate_between_tests(session: AsyncSession) -> None:
    assert (await session.scalar(select(User))) is None


async def test_package_version_unique_per_job(session: AsyncSession, user: User) -> None:
    job = Job(
        user_id=user.id,
        jd_text="text",
        dedupe_hash="pkg-version-uniq",
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    def make_package() -> Package:
        return Package(
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

    session.add(make_package())
    await session.commit()

    session.add(make_package())
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_next_version_never_counts_another_users_package_on_the_same_job(
    session: AsyncSession, user: User
) -> None:
    """`next_version` used to key only on `job_id`; since `jobs.id` is globally unique that is a
    no-op today, but a stray `packages` row for another user on this job -- a bug, or a shared
    job pool -- would otherwise inflate the next version this user's own package gets."""
    other = await get_or_create_user(session, "other-version@example.com")
    job = Job(
        user_id=user.id, jd_text="text", dedupe_hash="version-leak", discovered_at=datetime.now(UTC)
    )
    session.add(job)
    await session.flush()
    session.add(
        Package(
            user_id=other.id,
            job_id=job.id,
            track_id="t",
            version=99,
            status="draft",
            resume_json={},
            cover_note="",
            change_log="",
            guardrail_report_json={},
            jd_extract_json={},
        )
    )
    await session.commit()

    assert await package_repo.next_version(session, user.id, job.id) == 1


async def test_application_unique_per_user_and_job(session: AsyncSession, user: User) -> None:
    job = Job(
        user_id=user.id, jd_text="text", dedupe_hash="app-uniq", discovered_at=datetime.now(UTC)
    )
    session.add(job)
    await session.flush()

    def make_application() -> Application:
        return Application(
            user_id=user.id, job_id=job.id, status="queued", notes="", status_history_json=[]
        )

    session.add(make_application())
    await session.commit()

    session.add(make_application())
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_watchlist_unique_per_user_source_and_board(
    session: AsyncSession, user: User
) -> None:
    def make_entry() -> WatchlistEntry:
        return WatchlistEntry(
            user_id=user.id,
            company="ExampleCo",
            source="greenhouse",
            board="exampleco",
            keywords=[],
        )

    session.add(make_entry())
    await session.commit()

    session.add(make_entry())
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_job_score_unique_per_user_job_and_track(session: AsyncSession, user: User) -> None:
    job = Job(
        user_id=user.id, jd_text="text", dedupe_hash="score-uniq", discovered_at=datetime.now(UTC)
    )
    session.add(job)
    await session.flush()

    def make_score() -> JobScore:
        return JobScore(
            user_id=user.id, job_id=job.id, track_id="t", fit_score=50, scored_at=datetime.now(UTC)
        )

    session.add(make_score())
    await session.commit()

    session.add(make_score())
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_list_packages_ignores_another_users_application_on_the_same_job(
    session: AsyncSession, user: User
) -> None:
    """`Application.job_id == Package.job_id` alone (no `user_id` check) would let a stray
    Application row belonging to a different user attach to this user's package. Nothing reaches
    this through the API today -- the applications router always checks the job's owner first --
    but nothing at the schema level stops it either, and a shared job pool would make `job_id`
    alone insufficient to tell the two apart."""
    other = await get_or_create_user(session, "other-list-packages@example.com")
    job = Job(
        user_id=user.id, jd_text="text", dedupe_hash="leak-list", discovered_at=datetime.now(UTC)
    )
    session.add(job)
    await session.flush()
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
    session.add(
        Application(
            user_id=other.id, job_id=job.id, status="applied", notes="", status_history_json=[]
        )
    )
    await session.commit()

    rows = await package_repo.list_packages(session, user.id, applied=False)
    assert [p.id for p, _, _ in rows] == [package.id]
    assert rows[0][2] is None


async def test_needs_review_count_ignores_another_users_application_on_the_same_job(
    session: AsyncSession, user: User
) -> None:
    other = await get_or_create_user(session, "other-needs-review@example.com")
    job = Job(
        user_id=user.id, jd_text="text", dedupe_hash="leak-review", discovered_at=datetime.now(UTC)
    )
    session.add(job)
    await session.flush()
    session.add(
        Package(
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
    )
    session.add(
        Application(
            user_id=other.id, job_id=job.id, status="applied", notes="", status_history_json=[]
        )
    )
    await session.commit()

    assert await dashboard_repo.needs_review_count(session, user.id) == 1
