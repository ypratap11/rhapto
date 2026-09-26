import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_discovery_sources import fake_http_for
from test_poller import FakeAggregator

from rhapto.db.models import Aggregator, Job, JobScore, Task, User
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.services.discovery.poller import PollSummary
from rhapto.services.discovery.posting import Posting
from rhapto.services.eventbus import Event, InMemoryEventBus, task_channel
from rhapto.worker import tasks as worker_tasks
from rhapto.worker.main import cron_hours
from rhapto.worker.tasks import TASKS, poll_now, rescore_jobs, score_jobs


class JsonEncodingEventBus(InMemoryEventBus):
    """`InMemoryEventBus` hands events straight to subscribers without serializing them, so it
    would happily pass along a raw `uuid.UUID` that `RedisEventBus.publish` (a real `json.dumps`)
    cannot. Encode-then-decode here so a payload that is not JSON-safe fails the same way it
    would against Redis, instead of only failing in production."""

    async def publish(self, channel: str, event: Event) -> None:
        await super().publish(channel, json.loads(json.dumps(event)))


async def seed(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(
        session,
        user.id,
        Track(
            id="data-pm",
            name="Data",
            resume_base="b",
            min_fit=60,
            keywords=["ETL", "program manager"],
            description="Data platform program leadership",
        ),
    )
    await profile_repo.replace_watchlist(
        session,
        user.id,
        [WatchlistEntry(company="ExampleCo", source="greenhouse", board="exampleco")],
    )
    await session.commit()


class RecordingRedis:
    """A minimal arq-pool double: records every enqueue_job call, does not run anything."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue_job(self, task: str, **kwargs: Any) -> None:
        self.enqueued.append((task, kwargs))


def ctx_for(
    factory: async_sessionmaker[AsyncSession], bus: InMemoryEventBus, engine: AsyncEngine
) -> dict[str, Any]:
    return {
        "session_factory": factory,
        "engine": engine,
        "redis": RecordingRedis(),
        "embedder": FakeEmbeddingProvider(dimensions=384),
        "event_bus": bus,
        "discovery_http": fake_http_for("greenhouse"),
        "allow_dimension_mismatch": False,
    }


async def test_poll_now_runs_and_publishes(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
) -> None:
    await seed(session, user)
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    bus = InMemoryEventBus()
    events: list[dict[str, Any]] = []
    async with bus.subscription(task_channel(str(task.id))) as stream:
        await poll_now(ctx_for(session_factory, bus, engine), str(task.id))
        async for event in stream:
            events.append(event)
            if event["event"] in ("done", "error"):
                break
    assert events[-1]["event"] == "done" and events[-1]["new_jobs"] == 2
    assert [e["step"] for e in events if e["event"] == "progress"][:1] == ["fetch"]
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "succeeded" and row.result_ref == "new:2"
        assert len(list(await check.scalars(select(Job)))) == 2


async def test_poll_now_records_failure(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
) -> None:
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    bus = InMemoryEventBus()
    ctx = ctx_for(session_factory, bus, engine)
    del ctx[
        "embedder"
    ]  # KeyError at the poll_sources call site, i.e. at the task boundary, not inside one source
    events: list[dict[str, Any]] = []
    async with bus.subscription(task_channel(str(task.id))) as stream:
        await poll_now(ctx, str(task.id))
        async for event in stream:
            events.append(event)
            if event["event"] in ("done", "error"):
                break
    assert events[-1]["event"] == "error" and "embedder" in events[-1]["message"]
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "failed" and row.error


async def test_poll_now_reports_success_for_a_result_tied_to_a_saved_search(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    fake_aggregators: None,
    engine: AsyncEngine,
) -> None:
    """Regression test: a `RunResult` for a saved-search-driven aggregator carries a `uuid.UUID`
    `search_id`, which `json.dumps` cannot encode on its own. Before the fix, the "done" publish
    below raised, and the exception handler downgraded an already-succeeded task to "failed" and
    published an "error" event instead -- so `poll_now` looked like it failed even though it did
    not. See apps/web/src/components/jobs/TaskProgress.tsx, which turns any "error" event into a
    toast for the "Poll now" button on the Dashboard."""
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location=None, remote="include"
    )
    session.add(Aggregator(user_id=user.id, source="fake-agg", enabled=True, keywords=[]))
    await session.commit()
    FakeAggregator.postings = [
        Posting(
            external_id="1",
            company="ExampleCo",
            title="Alpha Engineer",
            location="Denver, CO",
            url="https://jobs.lever.co/exampleco/alpha",
            jd_text="alpha " * 20,
        )
    ]
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    bus = JsonEncodingEventBus()
    ctx = ctx_for(session_factory, bus, engine)
    events: list[dict[str, Any]] = []
    async with bus.subscription(task_channel(str(task.id))) as stream:
        await poll_now(ctx, str(task.id))
        async for event in stream:
            events.append(event)
            if event["event"] in ("done", "error"):
                break
    assert events[-1]["event"] == "done", events[-1]
    result = next(r for r in events[-1]["results"] if r["source"] == "fake-agg")
    assert result["search_id"] == str(search.id)
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "succeeded"


async def test_score_and_rescore_tasks(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
) -> None:
    await seed(session, user)
    job = Job(
        user_id=user.id,
        jd_text="ETL program manager for the data platform " * 5,
        title="Data Program Manager",
        dedupe_hash="h",
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.commit()
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)
    await score_jobs(ctx, str(user.id), [str(job.id)])
    async with session_factory() as check:
        scored = await check.get(Job, job.id)
        assert scored is not None and scored.best_track_id == "data-pm"

    async with session_factory() as reset:
        to_reset = await reset.get(Job, job.id)
        assert to_reset is not None
        to_reset.best_track_id = None
        to_reset.best_fit = None
        await reset.commit()

    await rescore_jobs(ctx, str(user.id))
    async with session_factory() as check:
        rescored = await check.get(Job, job.id)
        assert (
            rescored is not None
            and rescored.best_track_id == "data-pm"
            and rescored.best_fit is not None
        )
        scores = list(await check.scalars(select(JobScore).where(JobScore.job_id == job.id)))
        assert any(s.track_id == "data-pm" for s in scores)
    assert set(TASKS) >= {"poll_now", "poll_all_sources", "score_jobs", "rescore_jobs"}


async def test_poll_user_records_failure_without_raising(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed(session, user)

    async def fake_poll_sources(*args: Any, **kwargs: Any) -> PollSummary:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_tasks, "poll_sources", fake_poll_sources)
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)
    await worker_tasks.poll_user(ctx, str(user.id))  # must not raise despite the fetch failing


async def test_poll_user_opens_a_fresh_session_per_call(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
) -> None:
    """Regression guard for the shared-session bug Phase 0 already fixed: poll_user must call
    session_factory() fresh on every invocation, not hold one open across calls for different
    users. Fixes re-review item 7: the earlier version of this test only counted rows afterwards,
    which proves nothing about session identity -- this counts factory() invocations instead,
    which is what the Phase 0 bug (one shared AsyncSession, and therefore one identity map, across
    a whole per-user loop) was actually about.
    """
    other = await get_or_create_user(session, "other@example.com")
    await seed(session, user)
    await seed(session, other)
    await session.commit()

    call_count = 0
    real_factory = session_factory

    def counting_factory() -> Any:
        nonlocal call_count
        call_count += 1
        return real_factory()

    ctx = ctx_for(counting_factory, InMemoryEventBus(), engine)
    await worker_tasks.poll_user(ctx, str(user.id))
    await worker_tasks.poll_user(ctx, str(other.id))

    assert call_count == 2  # one fresh session per call, never reused across users


def test_cron_hours_from_interval() -> None:
    assert cron_hours(6) == {0, 6, 12, 18}
    assert cron_hours(24) == {0}
    assert cron_hours(5) == {0, 5, 10, 15, 20}
    assert cron_hours(0) == set()
