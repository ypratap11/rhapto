import asyncio

from rhapto.services.eventbus import InMemoryEventBus, task_channel


def test_task_channel() -> None:
    assert task_channel("abc") == "task:abc"


async def test_subscriber_receives_events_published_after_subscribing() -> None:
    bus = InMemoryEventBus()
    received: list[dict[str, object]] = []

    async def consume() -> None:
        async with bus.subscription("task:1") as events:
            async for event in events:
                received.append(event)
                if event.get("event") == "done":
                    break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await bus.publish("task:1", {"event": "progress", "step": "extract"})
    await bus.publish("task:2", {"event": "progress", "step": "ignored"})
    await bus.publish("task:1", {"event": "done"})
    await asyncio.wait_for(consumer, timeout=2)
    assert received == [{"event": "progress", "step": "extract"}, {"event": "done"}]
    assert bus.published[0] == ("task:1", {"event": "progress", "step": "extract"})


async def test_events_before_subscription_are_not_replayed() -> None:
    bus = InMemoryEventBus()
    await bus.publish("task:1", {"event": "progress", "step": "early"})
    async with bus.subscription("task:1") as events:
        await bus.publish("task:1", {"event": "done"})
        first = await asyncio.wait_for(events.__anext__(), timeout=1)
    assert first == {"event": "done"}


async def test_unsubscribe_on_exit() -> None:
    bus = InMemoryEventBus()
    async with bus.subscription("task:1"):
        assert bus.subscriber_count("task:1") == 1
    assert bus.subscriber_count("task:1") == 0
