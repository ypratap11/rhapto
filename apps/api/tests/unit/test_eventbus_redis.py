"""RedisEventBus against a real Redis. Skipped (with a message) when Redis is unreachable."""

import asyncio
import uuid

from rhapto.services.eventbus import RedisEventBus, task_channel


async def test_publish_subscribe_round_trip(test_redis_url: str) -> None:
    channel = task_channel(str(uuid.uuid4()))
    subscriber = RedisEventBus(test_redis_url)
    publisher = RedisEventBus(test_redis_url)
    try:
        async with subscriber.subscription(channel) as events:
            await publisher.publish(channel, {"event": "progress", "step": "extract"})
            first = await asyncio.wait_for(anext(events), timeout=5)
            await publisher.publish(
                channel, {"event": "done", "package_id": "p", "status": "draft"}
            )
            second = await asyncio.wait_for(anext(events), timeout=5)
    finally:
        await subscriber.close()
        await publisher.close()
    assert first == {"event": "progress", "step": "extract"}
    assert second == {"event": "done", "package_id": "p", "status": "draft"}


async def test_subscription_only_sees_events_on_its_channel(test_redis_url: str) -> None:
    mine = task_channel(str(uuid.uuid4()))
    theirs = task_channel(str(uuid.uuid4()))
    bus = RedisEventBus(test_redis_url)
    try:
        async with bus.subscription(mine) as events:
            await bus.publish(theirs, {"event": "progress", "step": "other"})
            await bus.publish(mine, {"event": "progress", "step": "mine"})
            event = await asyncio.wait_for(anext(events), timeout=5)
    finally:
        await bus.close()
    assert event == {"event": "progress", "step": "mine"}
