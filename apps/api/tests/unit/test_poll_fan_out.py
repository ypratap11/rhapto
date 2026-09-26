from __future__ import annotations

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

    enqueued_user_ids = {kwargs["user_id"] for _, kwargs in redis.enqueued if _ == "poll_user"}
    assert enqueued_user_ids == {str(u1_id), str(u2_id)}


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
