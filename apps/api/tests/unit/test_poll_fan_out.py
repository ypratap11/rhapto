from __future__ import annotations

from datetime import timedelta
from typing import Any

from rhapto.db.repositories.users import get_or_create_user
from rhapto.worker.tasks import poll_all_sources


class RecordingRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue_job(self, task: str, **kwargs: Any) -> None:
        self.enqueued.append((task, kwargs))


async def test_poll_all_sources_enqueues_one_poll_user_job_per_user(session_factory) -> None:
    async with session_factory() as session:
        u1 = await get_or_create_user(session, "one@example.com")
        u2 = await get_or_create_user(session, "two@example.com")
        await session.commit()
        u1_id, u2_id = u1.id, u2.id

    redis = RecordingRedis()
    await poll_all_sources({"session_factory": session_factory, "redis": redis})

    # M2: a set comprehension here would collapse a double-enqueue regression (each user enqueued
    # twice would still produce the same two-element set) -- assert the list length and task names
    # too, so "exactly once per user" is actually checked, not just "every user is somewhere".
    assert len(redis.enqueued) == 2
    assert {task for task, _ in redis.enqueued} == {"poll_user"}
    enqueued_user_ids = {kwargs["user_id"] for _, kwargs in redis.enqueued}
    assert enqueued_user_ids == {str(u1_id), str(u2_id)}
    # Carried over from Task 4: `_defer_by` staggers each user one minute after the last so N
    # queued polls can't occupy both worker slots back to back and starve an interactive job
    # behind the whole fan-out (I5). This had zero coverage -- deleting the `_defer_by` kwarg
    # entirely left this file green.
    assert [kwargs["_defer_by"] for _, kwargs in redis.enqueued] == [
        timedelta(0),
        timedelta(minutes=1),
    ]


async def test_poll_all_sources_enqueues_remaining_users_after_one_enqueue_fails(
    session_factory,
) -> None:
    """I1: the fan-out loop has to isolate one user's enqueue failure from the rest of the cycle.
    Verified against arq 0.28 (`worker.py:613,625`): a plain exception is a *terminal* job
    failure, not a retry -- retries only happen for `Retry`/`CancelledError`/`RetryJob` raised
    from *inside* a running job, which does not apply to a failed `enqueue_job` call itself. So a
    transient Redis error on user 1 of N must not silently drop 2..N for the whole cron cycle;
    the old inline loop's per-user `try/except` covered exactly this, and the dispatcher needs its
    own."""
    async with session_factory() as session:
        u1 = await get_or_create_user(session, "fails-to-enqueue@example.com")
        u2 = await get_or_create_user(session, "still-enqueued@example.com")
        await session.commit()
        u1_id, u2_id = u1.id, u2.id

    class FlakyRedis(RecordingRedis):
        async def enqueue_job(self, task: str, **kwargs: Any) -> None:
            if kwargs.get("user_id") == str(u1_id):
                raise ConnectionError("redis unreachable")
            await super().enqueue_job(task, **kwargs)

    redis = FlakyRedis()
    # Must not raise: one user's enqueue failure is caught and logged, not propagated.
    await poll_all_sources({"session_factory": session_factory, "redis": redis})

    enqueued_user_ids = [kwargs["user_id"] for _, kwargs in redis.enqueued]
    assert enqueued_user_ids == [str(u2_id)]


async def test_poll_all_sources_returns_without_polling_inline(
    session_factory, monkeypatch
) -> None:
    """The cron entry point must not call poll_sources itself -- that is poll_user's job now."""
    import rhapto.worker.tasks as tasks_module

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("poll_all_sources must not call poll_sources directly")

    monkeypatch.setattr(tasks_module, "poll_sources", boom)
    redis = RecordingRedis()
    await poll_all_sources({"session_factory": session_factory, "redis": redis})
