import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.scoring import (
    SCORE_CHUNK,
    ensure_track_embeddings,
    rescore_user,
    score_and_store,
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


async def test_score_and_store_sets_best_track_and_scores(
    session: AsyncSession, user: User
) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    await profile_repo.upsert_track(session, user.id, AI)
    job = await jobs_repo.create_job(
        session,
        user.id,
        jd_text="Own the data platform and ETL roadmap for analytics " * 5,
        title="Data Platform Program Manager",
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    await score_and_store(session, user.id, [job], embedder)
    assert (
        job.best_track_id == "data-pm" and job.best_fit is not None and job.jd_embedding is not None
    )
    tracks, vectors = await ensure_track_embeddings(session, user.id, embedder)
    assert set(vectors) == {"data-pm", "ai-pm"} and [t.id for t in tracks] == ["data-pm", "ai-pm"]
    assert await rescore_user(session, user.id, embedder) == 1


async def test_score_and_store_stores_the_location_tier_and_applies_it(
    session: AsyncSession, user: User
) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    await profile_repo.set_answers(
        session, user.id, {"location_preferred": "Santa Clara, Sunnyvale", "remote_ok": "yes"}
    )
    jd = "Own the data platform and ETL roadmap for analytics " * 5
    near = await jobs_repo.create_job(
        session, user.id, jd_text=jd, title="Data PM", location="Santa Clara, CA"
    )
    far = await jobs_repo.create_job(
        session, user.id, jd_text=jd + " abroad", title="Data PM", location="Dublin, Ireland"
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    await score_and_store(session, user.id, [near, far], embedder)

    assert near.location_tier == "preferred" and far.location_tier == "abroad"
    assert near.best_fit is not None and far.best_fit is not None
    # Same description, same track: the only thing separating the two scores is the location.
    assert far.best_fit < near.best_fit
    scores = await disc_repo.scores_for_jobs(session, user.id, [far.id])
    assert scores[far.id][0].rationale_json["location_tier"] == "abroad"


async def test_score_and_store_does_not_penalise_location_with_no_preference_set(
    session: AsyncSession, user: User
) -> None:
    """No `location_home`/`location_preferred` answer at all means no preference, not a
    penalty: a US posting scored with no preference expressed must land at the same fit as one
    explicitly tiered `preferred`."""
    await profile_repo.upsert_track(session, user.id, DATA)
    jd = "Own the data platform and ETL roadmap for analytics " * 5
    no_pref_job = await jobs_repo.create_job(
        session, user.id, jd_text=jd, title="Data PM", location="Denver, CO"
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    await score_and_store(session, user.id, [no_pref_job], embedder)
    assert no_pref_job.location_tier == "country"
    assert no_pref_job.best_fit is not None

    from rhapto.db.repositories.users import get_or_create_user

    other_user = await get_or_create_user(session, "other-pref@example.com")
    await profile_repo.upsert_track(session, other_user.id, DATA)
    await profile_repo.set_answers(session, other_user.id, {"location_preferred": "Boulder, CO"})
    preferred_job = await jobs_repo.create_job(
        session, other_user.id, jd_text=jd, title="Data PM", location="Denver, CO"
    )
    await score_and_store(session, other_user.id, [preferred_job], embedder)
    assert preferred_job.location_tier == "country"

    with_pref_job = await jobs_repo.create_job(
        session, other_user.id, jd_text=jd, title="Data PM", location="Boulder, CO"
    )
    await score_and_store(session, other_user.id, [with_pref_job], embedder)
    assert with_pref_job.location_tier == "preferred"

    # No preference at all: the "country" tier costs nothing, same fit as "preferred".
    assert no_pref_job.best_fit == with_pref_job.best_fit
    # A user who *did* express a preference still pays the usual "country" penalty.
    assert preferred_job.best_fit < with_pref_job.best_fit


async def test_rescore_user_picks_up_a_changed_location_preference(
    session: AsyncSession, user: User
) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    await profile_repo.set_answers(session, user.id, {"location_preferred": "Denver"})
    job = await jobs_repo.create_job(
        session,
        user.id,
        jd_text="Own the data platform and ETL roadmap for analytics " * 5,
        title="Data PM",
        location="Santa Clara, CA",
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    await score_and_store(session, user.id, [job], embedder)
    assert job.location_tier == "country"
    before = job.best_fit

    await profile_repo.set_answers(session, user.id, {"location_preferred": "Santa Clara"})
    assert await rescore_user(session, user.id, embedder) == 1
    assert job.location_tier == "preferred"
    assert job.best_fit is not None and before is not None and job.best_fit > before


class RecordingEmbedder(FakeEmbeddingProvider):
    """FakeEmbeddingProvider that remembers how many texts each call was handed."""

    def __init__(self) -> None:
        super().__init__(dimensions=384)
        self.sizes: list[int] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.sizes.append(len(texts))
        return await super().embed(texts)


async def test_score_and_store_embeds_in_chunks_and_tiers_every_row(
    session: AsyncSession, user: User
) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    jobs = [
        await jobs_repo.create_job(
            session,
            user.id,
            jd_text=f"Job {i}: own the data platform and ETL roadmap for analytics. " * 4,
            title=f"Data PM {i}",
            location="Denver, CO" if i % 2 else "Dublin, Ireland",
        )
        for i in range(120)
    ]
    embedder = RecordingEmbedder()
    await score_and_store(session, user.id, jobs, embedder)

    # One call for the single track, then the jobs in chunks of SCORE_CHUNK.
    assert embedder.sizes == [1, SCORE_CHUNK, SCORE_CHUNK, 120 - 2 * SCORE_CHUNK]
    assert all(size <= SCORE_CHUNK for size in embedder.sizes)
    assert [j.location_tier for j in jobs].count("country") == 60
    assert [j.location_tier for j in jobs].count("abroad") == 60
    assert all(j.best_fit is not None for j in jobs)


async def test_a_failing_chunk_leaves_the_other_chunks_and_every_tier_intact(
    session: AsyncSession, user: User
) -> None:
    class SecondChunkFails(RecordingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            if len(self.sizes) == 2:  # track call, first job chunk, then this one
                self.sizes.append(len(texts))
                raise RuntimeError("embedding provider is down")
            return await super().embed(texts)

    await profile_repo.upsert_track(session, user.id, DATA)
    jobs = [
        await jobs_repo.create_job(
            session,
            user.id,
            jd_text=f"Job {i}: own the data platform and ETL roadmap for analytics. " * 4,
            title=f"Data PM {i}",
            location="Denver, CO",
        )
        for i in range(60)
    ]
    await score_and_store(session, user.id, jobs, SecondChunkFails(), commit_each_chunk=True)

    for job in jobs:
        await session.refresh(job)
    assert all(j.location_tier == "country" for j in jobs)  # tiers never needed the embedding
    assert all(j.best_fit is not None for j in jobs[:SCORE_CHUNK])
    assert all(j.best_fit is None for j in jobs[SCORE_CHUNK:])


async def test_all_or_nothing_mode_propagates_a_chunk_failure(
    session: AsyncSession, user: User
) -> None:
    class AlwaysFails(RecordingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            if self.sizes:  # let the track embedding through, fail the first job chunk
                raise RuntimeError("embedding provider is down")
            return await super().embed(texts)

    await profile_repo.upsert_track(session, user.id, DATA)
    jobs = [
        await jobs_repo.create_job(
            session, user.id, jd_text="Own the ETL roadmap. " * 8, title="Data PM"
        )
    ]
    with pytest.raises(RuntimeError):
        await score_and_store(session, user.id, jobs, AlwaysFails())


async def test_a_failing_middle_chunk_does_not_stop_the_third_chunk(
    session: AsyncSession, user: User, caplog: pytest.LogCaptureFixture
) -> None:
    """A1. `session.rollback()` after chunk 2 expires every loaded Job; before the fix chunk 3 then
    read `job.jd_embedding` on an expired instance (MissingGreenlet) and failed too, and so did every
    chunk after it. The test above this one fails only the LAST chunk, so it never ran a chunk after
    a failure."""

    class MiddleChunkFails(RecordingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            if len(self.sizes) == 2:  # call 1 = the track, call 2 = chunk 1, this call = chunk 2
                self.sizes.append(len(texts))
                raise RuntimeError("embedding provider is down")
            return await super().embed(texts)

    await profile_repo.upsert_track(session, user.id, DATA)
    jobs = [
        await jobs_repo.create_job(
            session,
            user.id,
            jd_text=f"Job {i}: own the data platform and ETL roadmap for analytics. " * 4,
            title=f"Data PM {i}",
            location="Denver, CO",
        )
        for i in range(2 * SCORE_CHUNK + 20)  # three chunks: 50, 50, 20
    ]
    with caplog.at_level(logging.ERROR, logger="rhapto.services.scoring"):
        await score_and_store(session, user.id, jobs, MiddleChunkFails(), commit_each_chunk=True)

    for job in jobs:
        await session.refresh(job)
    assert all(j.best_fit is not None for j in jobs[:SCORE_CHUNK])
    assert all(j.best_fit is None for j in jobs[SCORE_CHUNK : 2 * SCORE_CHUNK])  # the failed chunk
    assert all(j.best_fit is not None for j in jobs[2 * SCORE_CHUNK :]), (
        "chunks after a failed chunk must still be scored"
    )
    assert caplog.text.count("scoring chunk") == 1  # only the middle chunk failed
    assert "MissingGreenlet" not in caplog.text
