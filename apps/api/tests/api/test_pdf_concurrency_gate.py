from __future__ import annotations

import asyncio
import threading
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, Package, User
from rhapto.services.storage import PackageStorage
from rhapto.worker import tasks as worker_tasks
from rhapto.worker.tasks import render_package_pdf


async def _make_package(
    session: AsyncSession, user: User, storage: PackageStorage, tag: str
) -> str:
    job = Job(
        user_id=user.id,
        source="manual",
        jd_text="A real job description. " * 6,
        dedupe_hash=f"hash-{tag}-{uuid.uuid4()}",
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    package = Package(
        user_id=user.id,
        job_id=job.id,
        track_id="pm",
        version=1,
        status="draft",
        resume_json={},
        cover_note="",
        change_log="",
        guardrail_report_json={},
        jd_extract_json={},
    )
    session.add(package)
    await session.flush()
    package.docx_path = str(storage.write_docx(str(package.id), b"fake docx bytes"))
    await session.commit()
    return str(package.id)


async def test_two_concurrent_renders_never_overlap(
    worker_ctx: dict[str, Any], user: User, session: AsyncSession, monkeypatch
) -> None:
    storage: PackageStorage = worker_ctx["storage"]
    session_factory: async_sessionmaker[AsyncSession] = worker_ctx["session_factory"]
    package_id_a = await _make_package(session, user, storage, "a")
    async with session_factory() as second_session:
        package_id_b = await _make_package(second_session, user, storage, "b")

    # Pre-warm two pooled connections concurrently. render_package_pdf(a) and (b) below each check
    # out one of their own via `session_factory()`; a pool only ever holds as many idle connections
    # as were checked out *at the same time*, so warming them up sequentially (one `async with`
    # after another) leaves exactly one idle connection behind -- the second one is always created
    # fresh. On this host a fresh asyncpg connection takes ~2s (localhost connection-setup cost,
    # not a query cost), which would otherwise swallow the whole 0.05s render window below and
    # serialise the two calls by accident, independent of whether `_PDF_RENDER_LOCK` exists. Warming
    # both connections up together, before the timed section, means the assertion below actually
    # measures render concurrency instead of connection-setup latency.
    async def _warm() -> None:
        async with session_factory() as warm_session:
            await warm_session.execute(text("SELECT 1"))

    await asyncio.gather(_warm(), _warm())

    # M1: `_PDF_RENDER_LOCK` is a module-level `asyncio.Lock()` created at import time; `Lock`
    # binds to whichever event loop first contends on it (verified: `acquire()` only calls
    # `_get_loop()` on the contended path), so this suite passes only because this is the sole
    # test that contends it. A second contending test anywhere in the process would raise
    # `RuntimeError: ... bound to a different event loop`, or -- worse -- a test cancelled while
    # holding it would leave `_locked = True` for every later test. Swapping in a fresh `Lock()`
    # scoped to this test's own event loop removes both risks; the production code reads the
    # module attribute at call time, so the patched instance is what `render_package_pdf` actually
    # takes.
    monkeypatch.setattr(worker_tasks, "_PDF_RENDER_LOCK", asyncio.Lock())

    concurrent = 0
    max_concurrent = 0
    # M8: `fake_render_pdf` runs on two different OS threads (via `asyncio.to_thread`), so the
    # plain `+= 1` / `-= 1` below is an unguarded read-modify-write race across threads -- an
    # interleaving that under-counts would make this test pass when it should fail, exactly the
    # failure mode the lock exists to catch. A `threading.Lock` (not `asyncio.Lock`, which is not
    # thread-safe) around the counter update makes the count itself trustworthy.
    counter_lock = threading.Lock()

    def fake_render_pdf(package_id: str, soffice_binary: str) -> None:
        nonlocal concurrent, max_concurrent
        with counter_lock:
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
        with counter_lock:
            concurrent -= 1
        return None

    # Patch the *instance*, not the class. `render_package_pdf` calls `storage.render_pdf(...)`;
    # patching PackageStorage.render_pdf at the class level makes that attribute lookup go through
    # the descriptor protocol, so Python binds `storage` as an implicit `self` and the call arrives
    # with three positional arguments against fake_render_pdf's two -- confirmed by actually running
    # it: `TypeError: fake_render_pdf() takes 2 positional arguments but 3 were given` (this test
    # failed to execute across three review rounds for exactly this reason). Assigning the plain
    # function directly to the instance's own `__dict__` skips the descriptor protocol entirely, so
    # the call reaches fake_render_pdf with exactly the two arguments it declares.
    monkeypatch.setattr(storage, "render_pdf", fake_render_pdf)
    await asyncio.gather(
        render_package_pdf(worker_ctx, package_id_a),
        render_package_pdf(worker_ctx, package_id_b),
    )
    assert max_concurrent == 1
