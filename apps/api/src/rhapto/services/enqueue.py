from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

TaskFn = Callable[..., Awaitable[None]]


class UnknownTaskError(KeyError):
    """The task name is not registered."""


class Enqueuer(Protocol):
    async def enqueue(self, task: str, **kwargs: Any) -> None: ...


class InlineEnqueuer:
    """Runs the task immediately in-process. Used by tests and by single-process demos."""

    def __init__(self, tasks: Mapping[str, TaskFn], ctx: dict[str, Any]) -> None:
        self._tasks = dict(tasks)
        self.ctx = ctx
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, task: str, **kwargs: Any) -> None:
        fn = self._tasks.get(task)
        if fn is None:
            raise UnknownTaskError(task)
        self.calls.append((task, dict(kwargs)))
        await fn(self.ctx, **kwargs)


class ArqEnqueuer:
    """Pushes jobs onto the arq queue in Redis."""

    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await create_pool(self._settings)

    async def enqueue(self, task: str, **kwargs: Any) -> None:
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        await self._pool.enqueue_job(task, **kwargs)

    async def close(self) -> None:
        if self._pool is not None:
            close = getattr(self._pool, "aclose", None) or self._pool.close
            await close()
            self._pool = None
