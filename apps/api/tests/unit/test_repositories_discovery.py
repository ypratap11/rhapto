from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import discovery as disc
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry


async def test_discovered_job_dedupe_and_repost(session: AsyncSession, user: User) -> None:
    first = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="1",
        company="ExampleCo",
        title="Data PM",
        location="Remote",
        url="https://example.com/1",
        jd_text="lead the data platform program " * 10,
        posted_at=None,
        identity_hash="abc",
        repost_of=None,
    )
    assert await jobs_repo.find_by_external_id(session, user.id, "greenhouse", "1") is first
    assert await jobs_repo.find_by_identity(session, user.id, "abc") is first
    again = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="2",
        company="ExampleCo",
        title="Data PM",
        location="Remote",
        url="https://example.com/2",
        jd_text="lead the data platform program again " * 10,
        posted_at=None,
        identity_hash="abc",
        repost_of=first.id,
    )
    assert again.repost_of == first.id and again.rescued is False


async def test_scores_upsert_and_list(session: AsyncSession, user: User) -> None:
    job = await jobs_repo.create_job(session, user.id, jd_text="x " * 60)
    await disc.upsert_scores(
        session, user.id, job, [("data-pm", 70, {"semantic": 60}), ("ai-pm", 20, {})]
    )
    await disc.upsert_scores(session, user.id, job, [("data-pm", 75, {"semantic": 65})])
    scores = await disc.scores_for_jobs(session, user.id, [job.id])
    by_track = {s.track_id: s.fit_score for s in scores[job.id]}
    assert by_track == {"data-pm": 75, "ai-pm": 20}


async def test_poll_runs_latest_and_consecutive_failures(session: AsyncSession, user: User) -> None:
    for error in ("boom", "boom", None, "boom", "boom", "boom"):
        run = await disc.start_run(session, user.id, "lever", "acme")
        disc.finish_run(run, found=0, new=0, error=error)
        await session.flush()
    other = await disc.start_run(session, user.id, "remoteok", None)
    disc.finish_run(other, found=3, new=1, error=None)
    await session.flush()
    latest = await disc.latest_runs(session, user.id)
    assert {(r.source, r.board) for r in latest} == {("lever", "acme"), ("remoteok", None)}
    assert await disc.consecutive_failures(session, user.id, "lever", "acme") == 3
    assert await disc.consecutive_failures(session, user.id, "remoteok", None) == 0


async def test_list_jobs_filters_and_sort(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(
        session, user.id, Track(id="data-pm", name="Data", resume_base="b", min_fit=60)
    )
    await profile_repo.upsert_track(
        session, user.id, Track(id="ai-pm", name="AI", resume_base="b", min_fit=50)
    )
    high = await jobs_repo.create_job(session, user.id, jd_text="high " * 60)
    low = await jobs_repo.create_job(session, user.id, jd_text="low " * 60)
    other = await jobs_repo.create_job(session, user.id, jd_text="other " * 60)
    high.best_track_id, high.best_fit = "data-pm", 80
    low.best_track_id, low.best_fit = "data-pm", 40
    other.best_track_id, other.best_fit = "ai-pm", 55
    await session.flush()
    fit = await jobs_repo.list_jobs(session, user.id, bucket="fit")
    assert [j.id for j in fit] == [high.id, other.id]
    assert [j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="low")] == [low.id]
    assert [j.id for j in await jobs_repo.list_jobs(session, user.id, track="ai-pm")] == [other.id]
    jobs_repo.set_rescued(low, True)
    await session.flush()
    assert low.id in [j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="fit")]
    newest = await jobs_repo.list_jobs(session, user.id, sort="newest")
    assert newest[0].id == other.id


async def test_list_jobs_bucket_covers_unscored_rescued_and_orphaned_track(
    session: AsyncSession, user: User
) -> None:
    await profile_repo.upsert_track(
        session, user.id, Track(id="data-pm", name="Data", resume_base="b", min_fit=60)
    )
    unscored = await jobs_repo.create_job(session, user.id, jd_text="unscored " * 60)
    rescued = await jobs_repo.create_job(session, user.id, jd_text="rescued " * 60)
    rescued.best_track_id, rescued.best_fit = "data-pm", 10
    jobs_repo.set_rescued(rescued, True)
    orphaned = await jobs_repo.create_job(session, user.id, jd_text="orphaned " * 60)
    # best_track_id names a track that was never created (deleted/renamed since scoring).
    orphaned.best_track_id, orphaned.best_fit = "ghost-track", 90
    await session.flush()

    fit_ids = {j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="fit")}
    low_ids = {j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="low")}

    # (1) rescued job stays in fit despite a low score.
    assert rescued.id in fit_ids and rescued.id not in low_ids
    # (2) an unscored job (best_fit is None) is visible in fit, never in low.
    assert unscored.id in fit_ids and unscored.id not in low_ids
    # (3) a scored job whose best_track_id has no track row counts as low, not fit.
    assert orphaned.id in low_ids and orphaned.id not in fit_ids


async def test_aggregators_replace_and_list(session: AsyncSession, user: User) -> None:
    await profile_repo.replace_aggregators(
        session, user.id, [AggregatorEntry(source="remoteok", enabled=True, keywords=["pm"])]
    )
    rows = await profile_repo.list_aggregators(session, user.id)
    assert [(r.source, r.enabled, r.keywords) for r in rows] == [("remoteok", True, ["pm"])]
