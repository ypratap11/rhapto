from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_worker_discovery import ctx_for

from rhapto.db.models import Task, User
from rhapto.db.repositories import tasks as task_repo
from rhapto.services.discovery.poller import PollSummary
from rhapto.services.eventbus import InMemoryEventBus, task_channel
from rhapto.worker import tasks as worker_tasks
from rhapto.worker.tasks import poll_now, with_user_poll_lock

# I4: with_user_poll_lock is the concurrency primitive the whole per-user fan-out depends on, and
# it had zero regression coverage -- replacing its body with `yield True` (no Postgres call, no
# lock, no unlock) left every other test in the suite green. Each test below is written to fail
# under exactly that mutation; see task-4-report.md for the confirmed break-check results.


async def test_lock_is_mutually_exclusive_and_releases_on_exit(
    engine: AsyncEngine, user: User
) -> None:
    async with with_user_poll_lock(engine, user.id) as outer:
        assert outer is True
        async with with_user_poll_lock(engine, user.id) as inner:
            assert inner is False  # same user, still held -- must not be acquired twice
    async with with_user_poll_lock(engine, user.id) as after_release:
        assert after_release is True  # the outer block's exit must have released it


async def test_lock_keys_do_not_collide_across_users(
    engine: AsyncEngine, user: User, session: AsyncSession
) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    other = await get_or_create_user(session, "poll-lock-other@example.com")
    await session.commit()
    async with with_user_poll_lock(engine, user.id) as a:
        async with with_user_poll_lock(engine, other.id) as b:
            assert a is True
            assert b is True  # a different user's lock is a different key, not a global lock


async def test_poll_user_does_not_poll_when_lock_already_held(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    async def counting_poll_sources(*args: Any, **kwargs: Any) -> PollSummary:
        nonlocal call_count
        call_count += 1
        raise AssertionError("poll_sources must not run while the lock is already held")

    monkeypatch.setattr(worker_tasks, "poll_sources", counting_poll_sources)
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)

    async with with_user_poll_lock(engine, user.id):  # hold the lock externally, as poll_now would
        await worker_tasks.poll_user(
            ctx, str(user.id)
        )  # must return quietly, not reach poll_sources

    # A call counter, not "did not raise": poll_user's own except-and-log would swallow the
    # AssertionError above just as readily as a correctly-skipped call, so only the counter proves
    # poll_sources was never reached.
    assert call_count == 0


async def test_poll_now_fails_the_task_when_the_lock_is_already_held(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    engine: AsyncEngine,
    user: User,
) -> None:
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    bus = InMemoryEventBus()
    events: list[dict[str, Any]] = []

    async with with_user_poll_lock(engine, user.id):  # hand-triggered poll loses the race
        async with bus.subscription(task_channel(str(task.id))) as stream:
            await poll_now(ctx_for(session_factory, bus, engine), str(task.id))
            async for event in stream:
                events.append(event)
                if event["event"] in ("done", "error"):
                    break

    assert events[-1] == {"event": "error", "message": "a poll is already running"}
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "failed"
        assert row.error == "a poll is already running for this account"
