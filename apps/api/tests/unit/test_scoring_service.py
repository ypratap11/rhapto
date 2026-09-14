from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import discovery as disc_repo
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
