from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.scoring import ensure_track_embeddings, rescore_user, score_and_store

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
