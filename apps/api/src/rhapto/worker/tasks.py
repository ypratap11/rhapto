from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import EMBEDDING_DIMENSIONS, Job, Task
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.profile import get_block
from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.select import block_text
from rhapto.engine.types import TailorRequest
from rhapto.services.enqueue import TaskFn
from rhapto.services.eventbus import EventBus, task_channel
from rhapto.services.profile_sync import block_row_to_model, load_profile_from_db
from rhapto.services.storage import PackageStorage


class WorkerContext(TypedDict):
    """Keys present in the arq `ctx` dict this worker's tasks rely on."""

    session_factory: async_sessionmaker[AsyncSession]
    llm: LLMProvider
    embedder: EmbeddingProvider
    event_bus: EventBus
    storage: PackageStorage
    soffice_binary: str


async def tailor_job(ctx: dict[str, Any], task_id: str) -> None:
    """Run the tailoring pipeline for the request stored on the task row; publish progress; persist the package."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    storage: PackageStorage = ctx["storage"]
    channel = task_channel(task_id)
    tid = uuid.UUID(task_id)

    async with factory() as session:
        task = await session.get(Task, tid)
        if task is None:
            return
        active_task: Task = task
        request = active_task.progress_json.get("request", {})
        task_repo.mark_running(active_task)
        await session.commit()
        user_id = active_task.user_id
        try:
            job = await session.get(Job, uuid.UUID(request["job_id"]))
            if job is None or job.user_id != user_id:
                raise ValueError("job not found for task")
            profile = await load_profile_from_db(session, user_id)
            previous = None
            parent_id = (
                uuid.UUID(request["parent_package_id"])
                if request.get("parent_package_id")
                else None
            )
            if parent_id is not None:
                parent = await package_repo.get_package(session, user_id, parent_id)
                if parent is None:
                    raise ValueError("parent package not found")
                previous = package_repo.package_row_to_model(
                    parent,
                    job_company=job.company or "",
                    job_title=job.title or "",
                    jd_text=job.jd_text,
                )

            async def on_step(step: str) -> None:
                task_repo.set_step(active_task, step)
                await session.commit()
                await bus.publish(channel, {"event": "progress", "step": step})

            result = await tailor(
                TailorRequest(
                    jd_text=job.jd_text,
                    track_id=request.get("track_id"),
                    feedback=request.get("feedback"),
                    previous_package=previous,
                ),
                profile,
                ctx["llm"],
                ctx["embedder"],
                on_step=on_step,
            )
            package = result.package
            version = await package_repo.next_version(session, job.id)
            package = package.model_copy(update={"version": version})
            row = await package_repo.create_package(
                session,
                user_id,
                job.id,
                package,
                selection_block_ids=result.selection.block_ids,
                parent_package_id=parent_id,
                docx_path=None,
                pdf_path=None,
            )
            if result.docx:
                row.docx_path = str(storage.write_docx(str(row.id), result.docx))
                pdf = storage.render_pdf(str(row.id), ctx["soffice_binary"])
                row.pdf_path = str(pdf) if pdf else None
            job.extracted_json = package.jd_extract.model_dump(mode="json")
            job.company = job.company or package.jd_extract.company
            job.title = job.title or package.jd_extract.title
            task_repo.mark_succeeded(active_task, str(row.id))
            await session.commit()
            await bus.publish(
                channel, {"event": "done", "package_id": str(row.id), "status": package.status}
            )
        except Exception as exc:  # task boundary: record and report, never crash the worker
            await session.rollback()
            failed_task = await session.get(Task, tid)
            if failed_task is not None:
                task_repo.mark_failed(failed_task, f"{type(exc).__name__}: {exc}")
                await session.commit()
            await bus.publish(channel, {"event": "error", "message": str(exc)})


async def embed_blocks(ctx: dict[str, Any], user_id: str, block_ids: list[str]) -> None:
    """Compute and store embeddings for the given blocks; unknown ids are ignored."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    embedder: EmbeddingProvider = ctx["embedder"]
    uid = uuid.UUID(user_id)
    async with factory() as session:
        rows = [
            r for r in [await get_block(session, uid, bid) for bid in block_ids] if r is not None
        ]
        if not rows:
            return
        vectors = await embedder.embed([block_text(block_row_to_model(r)) for r in rows])
        for row, vector in zip(rows, vectors, strict=True):
            # Providers may differ in width (the test fake is 64-dim); the column is fixed at EMBEDDING_DIMENSIONS.
            sized = list(vector[:EMBEDDING_DIMENSIONS]) + [0.0] * max(
                0, EMBEDDING_DIMENSIONS - len(vector)
            )
            row.embedding = sized
        await session.commit()


TASKS: dict[str, TaskFn] = {"tailor_job": tailor_job, "embed_blocks": embed_blocks}
