from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from rhapto.services.jobtext import html_to_text


@pytest.fixture(autouse=True)
def fast_switch() -> Iterator[None]:
    old = sys.getswitchinterval()
    sys.setswitchinterval(0.001)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


def burn(chunk: list[Any], seconds: float) -> list[Any]:
    """Spin on the CPU for a wall-clock deadline proportional to the chunk size."""
    end = time.perf_counter() + seconds * len(chunk)
    while time.perf_counter() < end:
        pass
    return list(chunk)


class Heartbeat:
    def __init__(self) -> None:
        self.max_gap = 0.0
        self._stop = False

    async def run(self) -> None:
        last = time.perf_counter()
        while not self._stop:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            self.max_gap = max(self.max_gap, now - last)
            last = now

    def stop(self) -> None:
        self._stop = True


async def _with_heartbeat(work: Any) -> float:
    hb = Heartbeat()
    task = asyncio.create_task(hb.run())
    await asyncio.sleep(0.02)
    try:
        await work
    finally:
        hb.stop()
        await task
    return hb.max_gap


def echo(chunk: list[Any]) -> list[Any]:
    return [x * 2 for x in chunk]


async def test_order_is_preserved_across_chunks() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    items = list(range(100))
    assert await parse_off_loop(echo, items, chunk=7) == echo(items)


async def test_empty_items_returns_empty_without_calling_fn() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    def boom(chunk: list[Any]) -> list[Any]:
        raise AssertionError("must not be called")

    assert await parse_off_loop(boom, []) == []


async def test_runs_off_the_loop_thread_and_passes_extra_args() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    seen: set[int] = set()

    names: set[str] = set()

    def fn(chunk: list[int], add: int) -> list[int]:
        seen.add(threading.get_ident())
        names.add(threading.current_thread().name)
        return [x + add for x in chunk]

    assert await parse_off_loop(fn, [1, 2, 3], 10) == [11, 12, 13]
    assert seen and threading.get_ident() not in seen
    # the dedicated pool, never the default executor (its threads are named asyncio_N)
    assert names and all(n.startswith("discovery-parse") for n in names)


async def test_chunk_sizes_are_bounded_by_default_and_by_argument() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    sizes: list[int] = []

    def record(chunk: list[int]) -> list[int]:
        sizes.append(len(chunk))
        return list(chunk)

    await parse_off_loop(record, list(range(80)))
    assert max(sizes) <= 25
    assert len(sizes) == 4
    sizes.clear()
    await parse_off_loop(record, list(range(80)), chunk=7)
    assert max(sizes) <= 7
    assert len(sizes) == 12


async def test_parallel_equals_serial_for_real_html_to_text() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    pages = [
        f"<div><h2>Role {i}</h2><p>Build <b>things</b> &amp; ship.</p>"
        f"<ul><li>Point {i}</li><li>Other</li></ul><script>x()</script></div>"
        for i in range(60)
    ]

    def convert(chunk: list[str]) -> list[str]:
        return [html_to_text(p) for p in chunk]

    serial = convert(pages)
    results = await asyncio.gather(*(parse_off_loop(convert, pages, chunk=5) for _ in range(4)))
    for r in results:
        assert r == serial


async def test_cancel_stops_further_submission() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    calls = 0

    def slow(chunk: list[int]) -> list[int]:
        nonlocal calls
        calls += 1
        time.sleep(0.2)
        return list(chunk)

    task = asyncio.create_task(parse_off_loop(slow, list(range(40)), chunk=1))
    await asyncio.sleep(0.3)
    calls_at_cancel = calls
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(1.0)
    assert calls <= calls_at_cancel + 1
    assert calls < 40


async def test_loop_stays_responsive_during_heavy_parse() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    gap = await _with_heartbeat(parse_off_loop(burn, list(range(80)), 0.025))
    assert gap < 0.25


async def test_small_source_that_also_parses_off_loop_finishes_while_heavy_parse_runs() -> None:
    from rhapto.services.discovery.offload import parse_off_loop

    heavy = asyncio.create_task(parse_off_loop(burn, list(range(80)), 0.025))
    start = time.perf_counter()
    for _ in range(3):
        await parse_off_loop(burn, list(range(4)), 0.005)
    await asyncio.sleep(0.05)
    elapsed = time.perf_counter() - start
    assert not heavy.done()
    assert elapsed < 1.0
    await heavy


async def test_inline_burn_starves_the_loop_control() -> None:
    async def inline() -> None:
        burn(list(range(80)), 0.025)

    gap = await _with_heartbeat(inline())
    assert gap >= 1.5
