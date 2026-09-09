from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, ResumeBlock, User
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
