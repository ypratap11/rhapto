from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_worker_discovery import ctx_for

from rhapto.db.models import JobScore, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.worker.tasks import (
    RESCORE_LOCK_CLASS,
    RESCORE_REQUEUE_DELAY,
    rescore_jobs,
    with_user_poll_lock,
    with_user_rescore_lock,
)

DATA = Track(
    id="data-pm",
    name="Data",
    resume_base="b",
    min_fit=60,
    keywords=["data platform", "ETL"],
    description="Data platform program leadership",
)
AI = Track(
    id="ai-pm",
    name="AI",
    resume_base="b",
    min_fit=55,
    keywords=["LLM", "GenAI"],
    description="AI product roles with LLM work",
)


class GatedEmbedder(FakeEmbeddingProvider):
    """Blocks inside the first JOB-chunk embed until released, so a test can act mid-run."""

    def __init__(self) -> None:
        super().__init__(dimensions=384)
        self.calls = 0
        self.in_job_chunk = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 2:  # call 1 embeds the track(s); call 2 is the first chunk of jobs
            self.in_job_chunk.set()
            await self.release.wait()
        return await super().embed(texts)


async def _seed(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    for i in range(3):
        await jobs_repo.create_job(
            session,
            user.id,
            jd_text=f"Job {i}: own the data platform and ETL roadmap for analytics. " * 4,
            title=f"Data PM {i}",
        )
    await session.commit()


async def _held_rescore_locks(engine: AsyncEngine) -> int:
    """Advisory locks of the rescore namespace held by ANY backend in this database right now.

    Asked of `pg_locks`, not by trying to re-acquire the lock: `pg_try_advisory_lock` is re-entrant
    within one backend session, so re-acquiring on the same pooled connection would succeed even if
    the release path were broken (plan review I-3).
    """
    async with engine.connect() as conn:
        held = await conn.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objsubid = 2 "
                "AND classid = :c AND database = "
                "(SELECT oid FROM pg_database WHERE datname = current_database())"
            ),
            {"c": RESCORE_LOCK_CLASS},
        )
        return int(held.scalar_one())


async def _scored_tracks(factory: async_sessionmaker[AsyncSession], user: User) -> set[str]:
    async with factory() as check:
        rows = await check.scalars(select(JobScore.track_id).where(JobScore.user_id == user.id))
        return set(rows)


async def test_lock_is_exclusive_per_user_and_released_on_exit(
    engine: AsyncEngine, user: User
) -> None:
    async with with_user_rescore_lock(engine, user.id) as first:
        assert first is True
        async with with_user_rescore_lock(engine, user.id) as second:
            assert second is False  # same user, still held: never acquired twice
    assert await _held_rescore_locks(engine) == 0  # released at the database, not just re-acquirable
    async with with_user_rescore_lock(engine, user.id) as after_release:
        assert after_release is True


async def test_rescore_lock_does_not_collide_with_the_poll_lock(
    engine: AsyncEngine, user: User
) -> None:
    """Own key namespace: a poll in flight must not block a rescore, nor the reverse."""
    async with with_user_poll_lock(engine, user.id) as polling:
        async with with_user_rescore_lock(engine, user.id) as rescoring:
            assert polling is True and rescoring is True


async def test_second_rescore_does_not_wait_and_the_final_scores_include_the_track_saved_mid_run(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    user: User,
) -> None:
    await _seed(session, user)
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)
    gated = GatedEmbedder()
    ctx["embedder"] = gated

    first = asyncio.create_task(rescore_jobs(ctx, str(user.id)))
    await asyncio.wait_for(gated.in_job_chunk.wait(), timeout=20)

    # The user saves a second role while the first run is mid-queue.
    async with session_factory() as other:
        await profile_repo.upsert_track(other, user.id, AI)
        await other.commit()

    # The second rescore must return promptly (it holds no worker slot and burns none of its own
    # timeout waiting) and must ask to be run again later instead of being dropped.
    await asyncio.wait_for(rescore_jobs(ctx, str(user.id)), timeout=5)
    assert ctx["redis"].enqueued == [
        ("rescore_jobs", {"user_id": str(user.id), "_defer_by": RESCORE_REQUEUE_DELAY})
    ]
    assert RESCORE_REQUEUE_DELAY == timedelta(seconds=30)
    assert not first.done()  # the first run is still blocked: the second really did not wait on it

    gated.release.set()
    await first
    # The first run read the track list before the second role existed.
    assert await _scored_tracks(session_factory, user) == {"data-pm"}
    assert await _held_rescore_locks(engine) == 0  # the finished run released its lock

    # The deferred copy arrives, finds the lock free and scores the track saved mid-run.
    ctx["embedder"] = FakeEmbeddingProvider(dimensions=384)
    await rescore_jobs(ctx, str(user.id))
    assert await _scored_tracks(session_factory, user) == {"data-pm", "ai-pm"}
    assert len(ctx["redis"].enqueued) == 1  # the free-lock run enqueued nothing further


async def test_cancelling_a_rescore_releases_the_lock(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    user: User,
) -> None:
    """arq cancels a job that exceeds job_timeout. The session-level lock must not outlive it, or
    that user could never be rescored again until the worker restarted."""
    await _seed(session, user)
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)
    gated = GatedEmbedder()
    ctx["embedder"] = gated

    running = asyncio.create_task(rescore_jobs(ctx, str(user.id)))
    await asyncio.wait_for(gated.in_job_chunk.wait(), timeout=20)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert await _held_rescore_locks(engine) == 0  # no backend still holds the lock
    async with with_user_rescore_lock(engine, user.id) as acquired:
        assert acquired is True
