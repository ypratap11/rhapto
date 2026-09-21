from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, TypedDict

from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.config import Settings, get_settings
from rhapto.db.models import EMBEDDING_DIMENSIONS, Job, Package, Task
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.profile import get_block
from rhapto.db.repositories.users import list_user_ids
from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.select import block_text
from rhapto.engine.types import TailorRequest
from rhapto.models.jd_extract import JDExtract
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.poller import poll_sources
from rhapto.services.documents import load_source
from rhapto.services.enqueue import TaskFn
from rhapto.services.eventbus import EventBus, task_channel
from rhapto.services.llm import (
    KEY_UNREADABLE_MESSAGE,
    LLMNotConfiguredError,
    provider_secrets,
    redact,
    resolve_llm,
)
from rhapto.services.packaging import persist_package
from rhapto.services.profile_sync import block_row_to_model, load_profile_from_db
from rhapto.services.scoring import rescore_user, score_and_store
from rhapto.services.secrets import KeyUnreadableError, SecretsError, fernet_for
from rhapto.services.storage import PackageStorage

logger = logging.getLogger("rhapto.worker")


LlmResolver = Callable[[AsyncSession, Settings, uuid.UUID], Awaitable[LLMProvider]]

# A provider key the user has to fix: the task fails with the message alone, because the exception
# class name tells them nothing they can act on.
SETUP_ERRORS = (LLMNotConfiguredError, SecretsError, ProviderAuthError)


class WorkerContext(TypedDict):
    """Keys present in the arq `ctx` dict this worker's tasks rely on."""

    session_factory: async_sessionmaker[AsyncSession]
    # Absent in the real worker (it resolves per task and per user); tests inject a double.
    llm_resolver: NotRequired[LlmResolver]
    embedder: EmbeddingProvider
    event_bus: EventBus
    storage: PackageStorage
    soffice_binary: str
    discovery_http: DiscoveryHttp


def _stored_extract(job: Job) -> JDExtract | None:
    """The JD extract already on the job row, or None when there is nothing usable there.

    A payload written by an older schema version would raise on validation; the run must not fail
    over a cache, so it is dropped and the pipeline extracts again.
    """
    if not job.extracted_json:
        return None
    try:
        return JDExtract.model_validate(job.extracted_json)
    except ValidationError:
        logger.warning("discarding unreadable extracted_json on job %s", job.id)
        return None


async def tailor_job(ctx: dict[str, Any], task_id: str) -> None:
    """Run the tailoring pipeline for the request stored on the task row; publish progress; persist the package."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    storage: PackageStorage = ctx["storage"]
    channel = task_channel(task_id)
    # Gathered before the work starts so the failure path can strip the user's keys out of whatever
    # a provider wrote in its message without doing any lookups while handling an error.
    secrets: tuple[str, ...] = ()

    async with factory() as session:
        try:
            tid = uuid.UUID(task_id)
            task = await session.get(Task, tid)
            if task is None:
                return
            active_task: Task = task
            request = active_task.progress_json.get("request", {})
            task_repo.mark_running(active_task)
            await session.commit()
            user_id = active_task.user_id
            settings = get_settings()
            secrets = await provider_secrets(session, settings, user_id)
            # Per task, not per worker: which provider runs this depends on whose task it is.
            resolver: LlmResolver = ctx.get("llm_resolver") or resolve_llm
            llm = await resolver(session, settings, user_id)

            job = await session.get(Job, uuid.UUID(request["job_id"]))
            if job is None or job.user_id != user_id:
                raise ValueError(f"job {request['job_id']} not found for task {task_id}")
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
                    raise ValueError(f"parent package {parent_id} not found")
                previous = package_repo.package_row_to_model(
                    parent,
                    job_company=job.company or "",
                    job_title=job.title or "",
                    jd_text=job.jd_text,
                )

            # Tune mode rewrites the user's own document, which is too big to ride along on the
            # task row: the request carries only the mode and the worker loads both halves here.
            mode = request.get("mode") or "blocks"
            source_document = None
            source_docx = None
            if mode == "tune":
                source = await load_source(session, storage, user_id)
                if source is None:
                    raise ValueError(
                        "no resume document stored; upload one before tailoring in tune mode"
                    )
                source_document, source_docx = source

            async def on_step(step: str) -> None:
                task_repo.set_step(active_task, step)
                await session.commit()
                await bus.publish(channel, {"event": "progress", "step": step})

            result = await tailor(
                TailorRequest(
                    jd_text=job.jd_text,
                    # `jd_text` is written once, at job creation, and never mutated, so an extract
                    # stored on the row cannot be stale -- reusing it saves one of the three LLM
                    # calls on every regenerate. A payload from an older schema is discarded rather
                    # than allowed to fail the run.
                    jd_extract=_stored_extract(job),
                    # An unspecified track follows the scorer's pick for THIS job. Without the
                    # fallback the engine's `get_track(None)` returns `tracks[0]` -- whichever
                    # track happens to be written first in tracks.yaml -- so every run that did
                    # not name a track silently used that one lens and the stored fit score was
                    # computed for nothing. `best_track_id` is None only on an unscored job, which
                    # still lands on the engine default.
                    track_id=request.get("track_id") or job.best_track_id,
                    feedback=request.get("feedback"),
                    previous_package=previous,
                    mode=mode,
                    source_document=source_document,
                    source_docx=source_docx,
                ),
                profile,
                llm,
                ctx["embedder"],
                on_step=on_step,
            )
            package = result.package
            # Commit the package row (inside persist_package) before touching LibreOffice so no
            # transaction is held open across the slow external subprocess call.
            if active_task.progress_json.get("step") != "render":
                task_repo.set_step(active_task, "render")
            row = await persist_package(
                session,
                user_id=user_id,
                job=job,
                package=package,
                selection_block_ids=list(result.selection.block_ids),
                parent_package_id=parent_id,
                storage=storage,
                docx=result.docx,
            )

            if row.docx_path is not None:
                pdf = await asyncio.to_thread(
                    storage.render_pdf, str(row.id), ctx["soffice_binary"]
                )
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
            try:
                failed_tid: uuid.UUID | None = uuid.UUID(task_id)
            except ValueError:
                failed_tid = None
            # `KeyUnreadableError` carries the operator's sentence ("RHAPTO_SECRET_KEY changed"),
            # which names an env var the end user cannot act on; the Jobs page gets the same
            # re-enter-your-key wording the API sends. Every other SecretsError is the operator's
            # to fix and keeps its own message, exactly as `api/errors.py` decides it.
            reportable = KEY_UNREADABLE_MESSAGE if isinstance(exc, KeyUnreadableError) else str(exc)
            detail = reportable if isinstance(exc, SETUP_ERRORS) else f"{type(exc).__name__}: {exc}"
            if failed_tid is not None:
                failed_task = await session.get(Task, failed_tid)
                if failed_task is not None:
                    task_repo.mark_failed(failed_task, redact(detail, *secrets))
                    await session.commit()
            await bus.publish(channel, {"event": "error", "message": redact(reportable, *secrets)})


async def render_package_pdf(ctx: dict[str, Any], package_id: str) -> None:
    """Render the PDF for an already-persisted package's DOCX, off the API's request path."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    storage: PackageStorage = ctx["storage"]
    async with factory() as session:
        row = await session.get(Package, uuid.UUID(package_id))
        if row is None or row.docx_path is None:
            return
        pdf = await asyncio.to_thread(storage.render_pdf, package_id, ctx["soffice_binary"])
        if pdf is not None:
            row.pdf_path = str(pdf)
        await session.commit()


async def embed_blocks(ctx: dict[str, Any], user_id: str, block_ids: list[str]) -> None:
    """Compute and store embeddings for the given blocks; unknown ids are ignored.

    A provider whose width is not EMBEDDING_DIMENSIONS means the deployment is misconfigured
    (wrong RHAPTO_EMBEDDING_MODEL): reshaping the vector would store semantically meaningless
    numbers and silently degrade selection, so the vector is dropped instead. Test fakes set
    `ctx["allow_dimension_mismatch"]` to opt into pad/truncate.
    """
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    embedder: EmbeddingProvider = ctx["embedder"]
    allow_mismatch = bool(ctx.get("allow_dimension_mismatch", False))
    try:  # task boundary: record and report, never crash the worker or be retried forever
        uid = uuid.UUID(user_id)
        async with factory() as session:
            rows = [
                r
                for r in [await get_block(session, uid, bid) for bid in block_ids]
                if r is not None
            ]
            if not rows:
                return
            vectors = await embedder.embed([block_text(block_row_to_model(r)) for r in rows])
            for row, vector in zip(rows, vectors, strict=True):
                values = list(vector)
                if len(values) != EMBEDDING_DIMENSIONS:
                    if not allow_mismatch:
                        logger.error(
                            "embedding provider returned %d dimensions, expected %d; not storing "
                            "an embedding for block %r (check RHAPTO_EMBEDDING_MODEL)",
                            len(values),
                            EMBEDDING_DIMENSIONS,
                            row.block_id,
                        )
                        continue
                    logger.warning(
                        "embedding provider returned %d dimensions, expected %d; padding or "
                        "truncating because allow_dimension_mismatch is set",
                        len(values),
                        EMBEDDING_DIMENSIONS,
                    )
                    values = values[:EMBEDDING_DIMENSIONS] + [0.0] * max(
                        0, EMBEDDING_DIMENSIONS - len(values)
                    )
                row.embedding = values
            await session.commit()
    except Exception:
        logger.exception("embed_blocks failed for user %s", user_id)
        return


DISCOVERY_CHANNEL = "discovery"


def _poll_fernet() -> Fernet | None:
    """The deployment's Fernet for keyed aggregators, or None so a deployment with no secret
    configured still polls its keyless sources instead of failing the whole poll."""
    try:
        return fernet_for(get_settings())
    except SecretsError:
        return None


async def poll_now(ctx: dict[str, Any], task_id: str) -> None:
    """User-triggered poll: progress on the task channel, summary on the discovery channel."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    channel = task_channel(task_id)
    async with factory() as session:
        tid: uuid.UUID | None = None
        try:
            tid = uuid.UUID(task_id)
            task = await session.get(Task, tid)
            if task is None:
                return
            active: Task = task
            task_repo.mark_running(active)
            await session.commit()

            async def on_step(step: str) -> None:
                task_repo.set_step(active, step)
                await session.commit()
                await bus.publish(channel, {"event": "progress", "step": step})

            summary = await poll_sources(
                session,
                active.user_id,
                http=ctx["discovery_http"],
                embedder=ctx["embedder"],
                on_step=on_step,
                fernet=_poll_fernet(),
            )
            task_repo.mark_succeeded(active, f"new:{summary.new_jobs}")
            await session.commit()
            # RunResult.search_id is a uuid.UUID | None, which json.dumps (RedisEventBus.publish)
            # cannot encode on its own -- stringify it here so the payload is JSON-safe. Getting
            # this wrong doesn't just break the event: mark_succeeded and commit above have
            # already run, so the poll's side effects persist while the publish below raises and
            # the caller reports the whole thing as a failure.
            results = [
                {**r.__dict__, "search_id": str(r.search_id) if r.search_id else None}
                for r in summary.results
            ]
            await bus.publish(
                channel, {"event": "done", "new_jobs": summary.new_jobs, "results": results}
            )
            await bus.publish(
                DISCOVERY_CHANNEL, {"event": "discovery", "new_jobs": summary.new_jobs}
            )
        except Exception as exc:  # task boundary: record and report, never crash the worker
            logger.exception("poll_now failed for task %s", task_id)
            await session.rollback()
            if tid is None:
                try:
                    tid = uuid.UUID(task_id)
                except ValueError:
                    tid = None
            if tid is not None:
                failed = await session.get(Task, tid)
                if failed is not None:
                    task_repo.mark_failed(failed, f"{type(exc).__name__}: {exc}")
                    await session.commit()
            await bus.publish(channel, {"event": "error", "message": str(exc)})


async def poll_all_sources(ctx: dict[str, Any]) -> None:
    """Cron entry point: poll every user's sources; failures are recorded per source."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    async with factory() as session:
        for user_id in await list_user_ids(session):
            try:
                summary = await poll_sources(
                    session,
                    user_id,
                    http=ctx["discovery_http"],
                    embedder=ctx["embedder"],
                    fernet=_poll_fernet(),
                )
                await bus.publish(
                    DISCOVERY_CHANNEL, {"event": "discovery", "new_jobs": summary.new_jobs}
                )
            except Exception:
                logger.exception("scheduled poll failed for user %s", user_id)
                await session.rollback()


async def score_jobs(ctx: dict[str, Any], user_id: str, job_ids: list[str]) -> None:
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    try:
        uid = uuid.UUID(user_id)
        async with factory() as session:
            jobs = [
                j
                for j in [await session.get(Job, uuid.UUID(i)) for i in job_ids]
                if j is not None and j.user_id == uid
            ]
            await score_and_store(session, uid, jobs, ctx["embedder"])
            await session.commit()
    except Exception:
        logger.exception("score_jobs failed for user %s", user_id)


async def rescore_jobs(ctx: dict[str, Any], user_id: str) -> None:
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    try:
        uid = uuid.UUID(user_id)
        async with factory() as session:
            await rescore_user(session, uid, ctx["embedder"])
            await session.commit()
    except Exception:
        logger.exception("rescore_jobs failed for user %s", user_id)


TASKS: dict[str, TaskFn] = {
    "tailor_job": tailor_job,
    "embed_blocks": embed_blocks,
    "render_package_pdf": render_package_pdf,
    "poll_now": poll_now,
    "poll_all_sources": poll_all_sources,
    "score_jobs": score_jobs,
    "rescore_jobs": rescore_jobs,
}
