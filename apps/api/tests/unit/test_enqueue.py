from typing import Any

import pytest

from rhapto.services.enqueue import InlineEnqueuer, UnknownTaskError


async def test_inline_enqueuer_runs_task_with_ctx() -> None:
    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def hello(ctx: dict[str, Any], **kwargs: Any) -> None:
        seen.append((ctx, kwargs))

    enqueuer = InlineEnqueuer({"hello": hello}, ctx={"llm": "fake"})
    await enqueuer.enqueue("hello", task_id="t1")
    assert seen == [({"llm": "fake"}, {"task_id": "t1"})]
    assert enqueuer.calls == [("hello", {"task_id": "t1"})]


async def test_inline_enqueuer_unknown_task() -> None:
    enqueuer = InlineEnqueuer({}, ctx={})
    with pytest.raises(UnknownTaskError):
        await enqueuer.enqueue("nope")
