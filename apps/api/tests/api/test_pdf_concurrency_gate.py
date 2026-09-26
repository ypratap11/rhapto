from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, Package, User
from rhapto.services.storage import PackageStorage
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

    concurrent = 0
    max_concurrent = 0

    def fake_render_pdf(package_id: str, soffice_binary: str) -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
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
