from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from test_discovery_sources import fake_http_for

from rhapto.db.models import Aggregator, Job, User, WatchlistEntry
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistModel
from rhapto.services.discovery import poller as poller_module
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.poller import PAUSED_MESSAGE, SourceSpec, build_specs, poll_sources
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES, get_source
from rhapto.services.discovery.sources.base import SourceError, SourceInfo

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


async def test_build_specs_fans_a_derived_search_per_track_across_enabled_aggregators(
    session: AsyncSession, user: User
) -> None:
    """With tracks and an enabled aggregator but no saved searches yet, build_specs derives one
    search per track (see derive_searches) and fans it out across every enabled aggregator --
    superseding the old one-spec-with-all-track-keywords behaviour."""
    await seed(session, user)
    specs = await build_specs(session, user.id)
    assert [(s.source, s.board, s.company) for s in specs] == [
        ("greenhouse", "exampleco", "ExampleCo"),
        ("remoteok", None, None),
        ("remoteok", None, None),
    ]
    aggregator_specs = specs[1:]
    assert [s.keywords for s in aggregator_specs] == [
        ["data platform", "ETL", "program manager"],
        ["LLM", "GenAI"],
    ]
    assert all(s.search is not None and s.search_id is not None for s in aggregator_specs)


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
    greenhouse_run = next(r for r in runs if r.source == "greenhouse")
    assert (greenhouse_run.found, greenhouse_run.new, greenhouse_run.error) == (2, 2, None)
    # remoteok is driven once per derived search (one per track): only the Data track's
    # keywords match the fixture job, so its run finds 1 while the AI track's finds 0.
    # latest_runs collapses same (source, board) runs to the newest, so check both directly.
    remoteok_runs = {(r.found, r.new, r.error) for r in summary.results if r.source == "remoteok"}
    assert remoteok_runs == {(1, 1, None), (0, 0, None)}

    again = await poll_sources(
        session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert again.new_jobs == 0
    assert {(r.source, r.found) for r in again.results} == {
        ("greenhouse", 2),
        ("remoteok", 1),
        ("remoteok", 0),
    }


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


async def test_poll_ingests_a_workday_watchlist_row(session: AsyncSession, user: User) -> None:
    """Workday boards are addressed by `<host prefix>/<site>`, and the watchlist row's company
    still wins over the tenant name the adapter falls back to."""
    for track in TRACKS:
        await profile_repo.upsert_track(session, user.id, track)
    await profile_repo.replace_watchlist(
        session,
        user.id,
        [
            WatchlistModel(
                company="ExampleCo",
                source="workday",
                board="exampleco.wd5/ExampleCoCareers",
                keywords=[],
            )
        ],
    )
    await profile_repo.replace_aggregators(session, user.id, [])
    await session.flush()

    http = fake_http_for("workday")
    summary = await poll_sources(
        session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert [(r.source, r.board, r.found, r.new, r.error) for r in summary.results] == [
        ("workday", "exampleco.wd5/ExampleCoCareers", 1, 1, None)
    ]
    job = await session.scalar(select(Job).where(Job.external_id == "exampleco:JR4001"))
    assert job is not None and job.company == "ExampleCo" and job.source == "workday"
    assert job.best_fit is not None and "<" not in job.jd_text
    # one paged search POST plus one detail GET, and nothing else
    assert [body["offset"] for _, _, body in http.posts] == [0]
    assert len(http.calls) == 1


class FakeAggregator:
    """Registered under a throwaway id so a poll can be driven without any HTTP at all."""

    info = SourceInfo("fake-agg", "aggregator", "Fake", False)
    seen: list[SearchSpec] = []
    postings: list[Posting] = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        type(self).seen.append(spec)
        return list(type(self).postings)


class KeyedAggregator(FakeAggregator):
    info = SourceInfo(
        "fake-keyed", "aggregator", "Fake keyed", False, needs_key=True, fields=("api_key",)
    )


@pytest.fixture
def fake_aggregators() -> Iterator[None]:
    FakeAggregator.seen = []
    FakeAggregator.postings = []
    SOURCES["fake-agg"] = FakeAggregator  # type: ignore[assignment]
    SOURCES["fake-keyed"] = KeyedAggregator  # type: ignore[assignment]
    yield
    SOURCES.pop("fake-agg", None)
    SOURCES.pop("fake-keyed", None)


async def test_every_active_search_runs_against_every_enabled_aggregator(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location="Denver, CO", remote="include"
    )
    await searches_repo.create_search(
        session, user.id, name="B", keywords=["beta"], location=None, remote="only"
    )
    # The pydantic AggregatorEntry model restricts `source` to the real, registered aggregator
    # ids, so a throwaway test id is inserted straight through the ORM row instead.
    session.add_all(
        [
            Aggregator(user_id=user.id, source="fake-agg", enabled=True, keywords=[]),
            Aggregator(user_id=user.id, source="fake-keyed", enabled=True, keywords=[]),
        ]
    )
    await session.flush()
    summary = await poll_sources(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        fernet=Fernet(Fernet.generate_key()),
    )
    assert [(s.name, s.keywords[0]) for s in FakeAggregator.seen] == [("A", "alpha"), ("B", "beta")]
    skipped = [r for r in summary.results if r.source == "fake-keyed"]
    assert len(skipped) == 2 and all(r.error == "no API key" for r in skipped)


async def test_a_result_on_a_lever_board_joins_the_watchlist_once(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location=None, remote="include"
    )
    session.add(Aggregator(user_id=user.id, source="fake-agg", enabled=True, keywords=[]))
    await session.flush()
    FakeAggregator.postings = [
        Posting(
            external_id="1",
            company="ExampleCo",
            title="Alpha Engineer",
            location="Denver, CO",
            url="https://jobs.lever.co/exampleco/abc",
            jd_text="alpha " * 20,
        )
    ]
    await session.flush()
    fernet = Fernet(Fernet.generate_key())
    await poll_sources(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        fernet=fernet,
    )
    rows = list(
        await session.scalars(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id))
    )
    assert [(r.source, r.board, r.discovered) for r in rows] == [("lever", "exampleco", True)]
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user.id)))
    assert [j.search_id for j in jobs] == [search.id]
    await poll_sources(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        fernet=fernet,
    )
    rows = list(
        await session.scalars(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id))
    )
    assert len(rows) == 1
