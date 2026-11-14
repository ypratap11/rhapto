from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# Dedicated pool, never the default executor: `assert_public_host` resolves DNS on the default
# executor, and CPU-bound parse chunks queued there would delay every outbound request.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="discovery-parse")


async def parse_off_loop[T, R](
    fn: Callable[..., list[R]], items: Sequence[T], *args: Any, chunk: int = 25
) -> list[R]:
    """Run `fn(chunk_of_items, *args)` over `items` in a worker thread, `chunk` items at a time.

    Chunks are awaited one after another, so the event loop gets control between chunks and a
    cancelled caller leaves at most one chunk in flight: nothing is submitted after a cancel.
    Order is preserved. `fn` must be a pure function (no shared mutable state, no I/O).
    """
    if not items:
        return []
    loop = asyncio.get_running_loop()
    out: list[R] = []
    for start in range(0, len(items), chunk):
        out += await loop.run_in_executor(_POOL, fn, list(items[start : start + chunk]), *args)
    return out
