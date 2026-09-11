import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from test_discovery_sources import fake_http_for

from rhapto.db.models import Job, User
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistModel
from rhapto.services.discovery import poller as poller_module
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.poller import PAUSED_MESSAGE, SourceSpec, build_specs, poll_sources
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.base import SourceError

TRACKS = [
    Track(
        id="data-pm",
        name="Data",
        resume_base="b",
        min_fit=60,
        keywords=["data platform", "ETL", "program manager"],
        description="Data platform program leadership",
    ),
    Track(
        id="ai-pm",
        name="AI",
        resume_base="b",
        min_fit=55,
        keywords=["LLM", "GenAI"],
        description="AI product roles",
    ),
]


async def seed(session: AsyncSession, user: User) -> None:
    for t in TRACKS:
        await profile_repo.upsert_track(session, user.id, t)
    await profile_repo.replace_watchlist(
        session,
        user.id,
        [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])],
    )
    await profile_repo.replace_aggregators(
        session,
        user.id,
        [
            AggregatorEntry(source="remoteok", enabled=True, keywords=[]),
            AggregatorEntry(source="hn-hiring", enabled=False),
        ],
    )
    await session.flush()


async def test_build_specs_uses_track_keywords_for_aggregators(
    session: AsyncSession, user: User
) -> None:
    await seed(session, user)
    specs = await build_specs(session, user.id)
    assert [(s.source, s.board, s.company) for s in specs] == [
        ("greenhouse", "exampleco", "ExampleCo"),
        ("remoteok", None, None),
    ]
    assert set(specs[1].keywords) == {"data platform", "ETL", "program manager", "LLM", "GenAI"}


async def test_poll_inserts_scores_and_records_runs(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp(
        {**fake_http_for("greenhouse").routes, **fake_http_for("remoteok").routes}
    )
    summary = await poll_sources(
        session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert summary.new_jobs == 3 and {r.source for r in summary.results} == {
        "greenhouse",
        "remoteok",
    }
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user.id)))
    assert {j.source for j in jobs} == {"greenhouse", "remoteok"}
    greenhouse = [j for j in jobs if j.source == "greenhouse"]
    assert all(
        j.company == "ExampleCo" and j.best_fit is not None and j.jd_embedding is not None
        for j in greenhouse
    )
    runs = await disc_repo.latest_runs(session, user.id)
    assert {(r.source, r.found, r.new, r.error) for r in runs} == {
        ("greenhouse", 2, 2, None),
        ("remoteok", 1, 1, None),
    }

    again = await poll_sources(
        session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert again.new_jobs == 0 and [r.found for r in again.results] == [2, 1]


async def test_repost_is_flagged_not_requeued(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    routes = fake_http_for("greenhouse").routes
    embedder = FakeEmbeddingProvider(dimensions=384)
    await poll_sources(session, user.id, http=FakeDiscoveryHttp(routes), embedder=embedder)
    key = next(iter(routes))
    reposted = {
        key: {
            "jobs": [
                {
                    **routes[key]["jobs"][0],
                    "id": 9999,
                    "content": "&lt;p&gt;Reposted with new wording.&lt;/p&gt;",
                }
            ]
        }
    }
    summary = await poll_sources(
        session, user.id, http=FakeDiscoveryHttp(reposted), embedder=embedder
    )
    assert summary.new_jobs == 1
    new = await session.scalar(select(Job).where(Job.external_id == "9999"))
    original = await session.scalar(select(Job).where(Job.external_id == "4001"))
    assert new is not None and original is not None and new.repost_of == original.id


async def test_failed_source_is_recorded_and_paused_after_three(
    session: AsyncSession, user: User
) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp(
        {"greenhouse.io": SourceError("HTTP 500"), "remoteok.com/api": [{"legal": "x"}]}
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    for _ in range(3):
        summary = await poll_sources(session, user.id, http=http, embedder=embedder)
        assert next(r for r in summary.results if r.source == "greenhouse").error == "HTTP 500"
    summary = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in summary.results if r.source == "greenhouse").error == PAUSED_MESSAGE
    assert (
        http.calls.count("https://boards-api.greenhouse.io/v1/boards/exampleco/jobs?content=true")
        == 3
    )
    # saving the watchlist entry (updated_at moves past the last run) lifts the pause
    await profile_repo.replace_watchlist(
        session,
        user.id,
        [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])],
    )
    await session.flush()
    summary = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in summary.results if r.source == "greenhouse").error == "HTTP 500"


async def test_explicit_specs_and_step_callbacks(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    steps: list[str] = []

    async def on_step(step: str) -> None:
        steps.append(step)

    spec = SourceSpec(
        source="greenhouse", board="exampleco", company="ExampleCo", keywords=["GenAI"]
    )
    summary = await poll_sources(
        session,
        user.id,
        http=fake_http_for("greenhouse"),
        embedder=FakeEmbeddingProvider(dimensions=384),
        specs=[spec],
        on_step=on_step,
    )
    assert summary.new_jobs == 1 and steps == ["fetch", "dedupe", "score", "done"]


async def test_existing_job_text_match_is_flagged_as_repost_not_skipped(
    session: AsyncSession, user: User
) -> None:
    """A posting whose jd_text hash matches an EXISTING job (here, a manually pasted one) must
    still be inserted and flagged with repost_of -- only an in-batch duplicate is skipped."""
    await seed(session, user)
    http = fake_http_for("greenhouse")
    postings = await get_source("greenhouse").fetch(http, board="exampleco", keywords=[])
    first = next(p for p in postings if p.external_id == "4001")
    manual = await jobs_repo.create_job(session, user.id, jd_text=first.jd_text)
    await session.flush()

    spec = SourceSpec(source="greenhouse", board="exampleco", company="ExampleCo", keywords=[])
    summary = await poll_sources(
        session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384), specs=[spec]
    )
    discovered = await session.scalar(select(Job).where(Job.external_id == "4001"))
    assert discovered is not None and discovered.repost_of == manual.id
    assert discovered.id in summary.new_job_ids


async def test_explicit_spec_with_no_entry_is_never_paused(
    session: AsyncSession, user: User
) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp({"greenhouse.io": SourceError("HTTP 500")})
    embedder = FakeEmbeddingProvider(dimensions=384)
    spec = SourceSpec(source="greenhouse", board="exampleco", company="ExampleCo", keywords=[])
    for _ in range(4):
        summary = await poll_sources(session, user.id, http=http, embedder=embedder, specs=[spec])
        assert summary.results[0].error == "HTTP 500"


async def test_ingest_failure_rolls_back_but_keeps_run_and_other_sources(
    session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(session, user)
    # A real mid-transaction rollback (triggered below) expires every ORM instance already
    # loaded on this shared session -- including `user` -- so capture the plain UUID now and
    # use it for every session call below rather than re-reading the (soon to be stale) `user`
    # attribute outside of an awaited SQLAlchemy call.
    user_id = user.id
    http = FakeDiscoveryHttp(
        {**fake_http_for("greenhouse").routes, **fake_http_for("remoteok").routes}
    )
    embedder = FakeEmbeddingProvider(dimensions=384)
    original = poller_module.jobs_repo.create_discovered_job

    async def boom(session, user_id, *, source, **kwargs):  # noqa: ANN001, ANN202
        if source == "greenhouse":
            raise IntegrityError("x", {}, Exception())
        return await original(session, user_id, source=source, **kwargs)

    monkeypatch.setattr(poller_module.jobs_repo, "create_discovered_job", boom)
    summary = await poll_sources(session, user_id, http=http, embedder=embedder)

    assert {r.source for r in summary.results} == {"greenhouse", "remoteok"}
    greenhouse_result = next(r for r in summary.results if r.source == "greenhouse")
    assert greenhouse_result.error is not None and "IntegrityError" in greenhouse_result.error
    remoteok_result = next(r for r in summary.results if r.source == "remoteok")
    assert remoteok_result.error is None and remoteok_result.new == 1

    runs = await disc_repo.latest_runs(session, user_id)
    greenhouse_run = next(r for r in runs if r.source == "greenhouse")
    assert greenhouse_run.error is not None and "IntegrityError" in greenhouse_run.error


async def test_resaving_the_entry_grants_three_fresh_attempts(
    session: AsyncSession, user: User
) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp({"greenhouse.io": SourceError("HTTP 500"), "remoteok.com/api": []})
    embedder = FakeEmbeddingProvider(dimensions=384)
    for _ in range(3):
        await poll_sources(session, user.id, http=http, embedder=embedder)
    paused = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in paused.results if r.source == "greenhouse").error == PAUSED_MESSAGE
    await profile_repo.replace_watchlist(
        session,
        user.id,
        [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])],
    )
    await session.flush()
    # Three attempts after the save, all failing, before the pause returns.
    for _ in range(3):
        summary = await poll_sources(session, user.id, http=http, embedder=embedder)
        assert next(r for r in summary.results if r.source == "greenhouse").error == "HTTP 500"
    summary = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in summary.results if r.source == "greenhouse").error == PAUSED_MESSAGE
