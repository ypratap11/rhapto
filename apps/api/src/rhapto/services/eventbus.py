from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

import redis.asyncio as aioredis

Event = dict[str, Any]


def task_channel(task_id: str) -> str:
    return f"task:{task_id}"


class EventBus(Protocol):
    async def publish(self, channel: str, event: Event) -> None: ...

    def subscription(self, channel: str) -> AbstractAsyncContextManager[AsyncIterator[Event]]: ...


class InMemoryEventBus:
    """Process-local pub/sub for tests and single-process runs. Subscribers only see events published after they subscribe."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Event]]] = {}
        self.published: list[tuple[str, Event]] = []

    async def publish(self, channel: str, event: Event) -> None:
        self.published.append((channel, event))
        for queue in list(self._queues.get(channel, [])):
            queue.put_nowait(event)

    def subscriber_count(self, channel: str) -> int:
        return len(self._queues.get(channel, []))

    @asynccontextmanager
    async def subscription(self, channel: str) -> AsyncIterator[AsyncIterator[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._queues.setdefault(channel, []).append(queue)

        async def events() -> AsyncGenerator[Event, None]:
            while True:
                yield await queue.get()

        gen = events()
        try:
            yield gen
        finally:
            await gen.aclose()
            self._queues[channel].remove(queue)
            if not self._queues[channel]:
                del self._queues[channel]


class RedisEventBus:
    """Redis pub/sub; events are JSON objects."""

    def __init__(self, url: str) -> None:
        self._redis = aioredis.from_url(url, decode_responses=True)  # type: ignore[no-untyped-call]

    async def publish(self, channel: str, event: Event) -> None:
        await self._redis.publish(channel, json.dumps(event))

    @asynccontextmanager
    async def subscription(self, channel: str) -> AsyncIterator[AsyncIterator[Event]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        async def events() -> AsyncGenerator[Event, None]:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                data = message["data"]
                yield json.loads(data) if isinstance(data, str) else data

        gen = events()
        try:
            yield gen
        finally:
            await gen.aclose()
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        await self._redis.aclose()
