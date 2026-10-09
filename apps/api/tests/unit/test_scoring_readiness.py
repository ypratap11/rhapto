"""Readiness (spec 3.3): a track is ready only when a rescore that started after its last save has
FINISHED. Real multi-chunk rescores; the only patch is `SCORE_CHUNK`, so there are several commits to
observe between."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, User
from rhapto.db.models import Track as TrackRow
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services import scoring as scoring_service
from rhapto.services.scoring import ensure_track_embeddings, rescore_user

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
JOBS = 5  # with SCORE_CHUNK patched to 2: chunks of 2, 2, 1


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scoring_service, "SCORE_CHUNK", 2)


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    tracks: tuple[Track, ...] = (DATA,),
) -> None:
    async with session_factory() as s:
        for track in tracks:
            await profile_repo.upsert_track(s, user.id, track)
        for i in range(JOBS):
            await jobs_repo.create_job(
                s,
                user.id,
                jd_text=f"Job {i}: own the data platform and ETL roadmap for analytics. " * 4,
                title=f"Data PM {i}",
                location="Denver, CO",
            )
        await s.commit()


async def _ready(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, track_id: str = "data-pm"
) -> bool | None:
    async with session_factory() as s:
        return await profile_repo.track_readiness(s, user_id, track_id)


async def _scored_jobs(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> int:
    async with session_factory() as s:
        return int(
            await s.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.user_id == user_id, Job.best_track_id.is_not(None))
            )
            or 0
        )


class Observing(FakeEmbeddingProvider):
    """Runs `hook(call_number)` before the Nth embed call. Call 1 embeds the track(s); call 2 is the
    first chunk of jobs; call 3 the second, by which time chunk 1 has COMMITTED."""

    def __init__(self, hook: Callable[[int], Awaitable[None]]) -> None:
        super().__init__(dimensions=384)
        self.calls = 0
        self.hook = hook

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        await self.hook(self.calls)
        return await super().embed(texts)


async def test_a_new_track_is_not_ready(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session_factory, user)
    assert await _ready(session_factory, user.id) is False
    assert await _ready(session_factory, user.id, "no-such-track") is None


async def test_readiness_is_false_between_chunks_and_true_after_the_final_commit(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    """The discriminating test. Mid-run, chunk 1 has COMMITTED: scored jobs and a best_track_id
    already exist, which is exactly what made 'a score exists / the track filter matches' (the
    withdrawn probe) declare completion early. Readiness must still be False, and must flip only
    after the rescore's own final commit."""
    await _seed(session_factory, user)
    seen: list[tuple[int, bool | None, int]] = []

    async def observe(call: int) -> None:
        if call >= 3:  # chunk 1 (and later chunk 2) are committed
            seen.append(
                (
                    call,
                    await _ready(session_factory, user.id),
                    await _scored_jobs(session_factory, user.id),
                )
            )

    async with session_factory() as work:
        await rescore_user(work, user.id, Observing(observe))
        # MUTANT RUN ONLY: pre-commit assertion disabled so the mid-run assertion is what fails.
        # assert await _ready(session_factory, user.id) is False
        await work.commit()

    assert len(seen) >= 2
    assert all(ready is False for _, ready, _ in seen), seen
    assert all(scored > 0 for _, _, scored in seen), (
        "scores must already exist mid-run, or this test proves nothing"
    )
    assert await _ready(session_factory, user.id) is True


async def test_a_save_during_a_rescore_is_not_marked_ready_by_it(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    """Stale-start race. A track is saved (and a second one created) while a rescore that started
    earlier is running. That rescore must not mark the re-saved track ready, and must not mark the
    new one at all; the next rescore does."""
    await _seed(session_factory, user)
    done = False

    async def save_mid_run(call: int) -> None:
        nonlocal done
        if call == 2 and not done:  # first chunk of jobs; the rescore has already read its tracks
            done = True
            async with session_factory() as other:
                await profile_repo.upsert_track(
                    other,
                    user.id,
                    DATA.model_copy(update={"keywords": ["data platform", "ETL", "warehouse"]}),
                )
                await profile_repo.upsert_track(other, user.id, AI)
                await other.commit()

    async with session_factory() as work:
        await rescore_user(work, user.id, Observing(save_mid_run))
        await work.commit()

    assert (
        await _ready(session_factory, user.id, "data-pm") is False
    )  # saved after this rescore started
    assert (
        await _ready(session_factory, user.id, "ai-pm") is False
    )  # not in the set this rescore loaded

    async with session_factory() as work:
        await rescore_user(work, user.id, FakeEmbeddingProvider(dimensions=384))
        await work.commit()
    assert await _ready(session_factory, user.id, "data-pm") is True
    assert await _ready(session_factory, user.id, "ai-pm") is True


async def test_embedding_only_write_leaves_readiness_unchanged(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    """The poller's `ensure_track_embeddings` rewrites a track's vector, which bumps `updated_at`
    (TimestampMixin onupdate). Readiness must not depend on `updated_at`, or every poll would flip a
    ready coach back to waiting (architect ruling)."""
    await _seed(session_factory, user)
    async with session_factory() as work:
        await rescore_user(work, user.id, FakeEmbeddingProvider(dimensions=384))
        await work.commit()
    assert await _ready(session_factory, user.id) is True

    async with session_factory() as other:
        for row in await profile_repo.list_tracks(other, user.id):
            row.embedding = None
        await other.commit()
        await ensure_track_embeddings(other, user.id, FakeEmbeddingProvider(dimensions=384))
        await other.commit()

    async with session_factory() as check:
        row = (
            await check.execute(
                select(TrackRow.updated_at, TrackRow.scored_at).where(TrackRow.user_id == user.id)
            )
        ).one()
    assert row.updated_at > row.scored_at, "setup: updated_at really did move past scored_at"
    assert await _ready(session_factory, user.id) is True


async def test_a_rescore_that_raises_never_marks(
    session_factory: async_sessionmaker[AsyncSession], user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(session_factory, user)

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("embedding provider is down")

    monkeypatch.setattr(scoring_service, "score_and_store", boom)
    async with session_factory() as work:
        with pytest.raises(RuntimeError):
            await rescore_user(work, user.id, FakeEmbeddingProvider(dimensions=384))
        await work.commit()
    assert await _ready(session_factory, user.id) is False


async def test_a_failed_chunk_still_marks_the_track(
    session_factory: async_sessionmaker[AsyncSession], user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Incremental mode keeps going past a bad chunk (existing behaviour); the run finished, so the
    track is ready. Jobs in the failed chunk keep their previous scores."""
    await _seed(session_factory, user)

    async def bad_chunk(*args: object, **kwargs: object) -> None:
        raise RuntimeError("bad chunk")

    monkeypatch.setattr(scoring_service, "_score_chunk", bad_chunk)
    async with session_factory() as work:
        await rescore_user(work, user.id, FakeEmbeddingProvider(dimensions=384))
        await work.commit()
    assert await _ready(session_factory, user.id) is True


async def test_a_deleted_track_is_simply_gone(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session_factory, user, (DATA, AI))
    async with session_factory() as s:
        await profile_repo.delete_track(s, user.id, "ai-pm")
        await s.commit()
    assert await _ready(session_factory, user.id, "ai-pm") is None
