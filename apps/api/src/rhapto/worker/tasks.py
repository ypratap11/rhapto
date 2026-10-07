from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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
from rhapto.services.trial import (
    TrialLimitExceededError,
    consume_trial_run,
    on_deployment_key,
)

logger = logging.getLogger("rhapto.worker")

# Serialises every LibreOffice invocation process-wide: two concurrent renders cost ~200-300MB
# each on top of the worker's ~1.87GB resident set, and max_jobs=2 means two PDF renders are
# otherwise reachable at once -- an OOM the box can already hit with one user and two queued
# packages (architecture.md §2.1). Shared by render_package_pdf and tailor_job's own PDF step,
# since both reach the same `storage.render_pdf` call.
_PDF_RENDER_LOCK = asyncio.Lock()


LlmResolver = Callable[[AsyncSession, Settings, uuid.UUID], Awaitable[LLMProvider]]

# A provider key the user has to fix: the task fails with the message alone, because the exception
# class name tells them nothing they can act on.
SETUP_ERRORS = (LLMNotConfiguredError, SecretsError, ProviderAuthError, TrialLimitExceededError)

# Shown instead of the provider's own words when the rejected key belongs to the deployment rather
# than to the person reading it. Names no provider, no model, no account and no balance.
SHARED_KEY_REJECTED_MESSAGE = (
    "This instance's shared LLM key was refused by its provider. Add your own key in Settings to "
    "keep going, or ask whoever runs this instance to check it."
)


@asynccontextmanager
async def with_user_poll_lock(engine: AsyncEngine, user_id: uuid.UUID) -> AsyncIterator[bool]:
    """A Postgres transaction-level advisory lock keyed on `user_id`, so the cron's `poll_user`
    and a hand-triggered `poll_now` can never interleave for the same user (audit B11). Non-blocking
    (`pg_try_advisory_xact_lock`): the caller that loses the race skips its poll for this cycle
    rather than queuing behind the other one, which is the right trade for a cron that runs again
    on its own schedule. Transaction-scoped, not session-scoped: the lock is released the instant
    this connection's implicit transaction ends -- on commit *or* rollback, which is what
    `engine.connect()` issues on close if nothing else did -- so there is no `pg_advisory_unlock`
    to forget. A session-scoped lock plus a missed unlock would otherwise poison a pooled
    connection permanently: a plain pool checkin issues ROLLBACK, which does not release a
    session-scoped advisory lock, so that user could never poll again until the worker restarted
    (M6). Opens its own connection so the lock's transaction is not shared with -- and cannot be
    ended early by -- a caller's own `AsyncSession` work.
    """
    key = int.from_bytes(user_id.bytes[:8], "big", signed=True)
    async with engine.connect() as conn:
        acquired = bool(
            (await conn.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": key})).scalar()
        )
        yield acquired


#: First half of the two-int advisory-lock key (ASCII "RESC"). Postgres keeps `pg_advisory_lock(int, int)`
#: and `pg_advisory_lock(bigint)` in separate key spaces, so no rescore key can equal a poll key.
RESCORE_LOCK_CLASS = 0x52455343

#: How long a rescore that lost the race waits before asking to run again.
RESCORE_REQUEUE_DELAY = timedelta(seconds=30)


@asynccontextmanager
async def with_user_rescore_lock(engine: AsyncEngine, user_id: uuid.UUID) -> AsyncIterator[bool]:
    """A NON-blocking, SESSION-level advisory lock keyed on `user_id`, for one whole `rescore_jobs`.

    Session-level, not transaction-level like `with_user_poll_lock`: `rescore_user` commits after
    every chunk, which would release a transaction-level lock after the first one. That is also why
    this holds its own dedicated connection, in AUTOCOMMIT so no transaction sits open for minutes.

    Non-blocking (`pg_try_advisory_lock`): a rescore that loses the race must neither sit in one of
    the worker's two slots nor spend its own `job_timeout` waiting (re-review R3-1); the caller
    re-enqueues itself instead. Cleanup is unconditional: the lock is released in `finally`, then
    the connection is invalidated, so it can never return to the pool still holding the lock -- a
    session-level lock plus a missed unlock would otherwise poison a pooled connection (see the
    note on `with_user_poll_lock`). Invalidation ends the backend session, which releases any
    advisory lock it still holds, even when the unlock itself was skipped by a cancellation.

    The key uses 4 bytes of the user's UUID, so two users can in principle share a key; that only
    serialises their rescores, which is harmless.
    """
    key = int.from_bytes(user_id.bytes[:4], "big", signed=True)
    params = {"c": RESCORE_LOCK_CLASS, "k": key}
    conn = await engine.connect()
    try:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        acquired = bool(
            (
                await conn.execute(
                    text("SELECT pg_try_advisory_lock(CAST(:c AS integer), CAST(:k AS integer))"),
                    params,
                )
            ).scalar()
        )
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    await conn.execute(
                        text("SELECT pg_advisory_unlock(CAST(:c AS integer), CAST(:k AS integer))"),
                        params,
                    )
                except Exception:  # invalidate() below releases it anyway
                    logger.exception("could not release the rescore lock for user %s", user_id)
    finally:
        await conn.invalidate()
        await conn.close()


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
            # ctx first (set by on_startup, and by the API tests' worker_ctx fixture); the
            # `get_settings()` fallback keeps a hand-built ctx working. See worker/main.py.
            settings: Settings = ctx.get("settings") or get_settings()
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

            # Money is about to be spent. Claim one run and get the claim COMMITTED before the
            # first model call: a worker killed mid-run must not hand out a free one, and there is
            # deliberately no refund path. Placed after the job, profile and (tune-mode) document
            # loads, so a run that dies on a missing document or an unimportable profile burns
            # nothing. The marker on the task row makes an arq re-delivery idempotent -- a retry
            # re-runs the pipeline but must not be charged twice. Dict reassignment, not in-place
            # mutation, matching `task_repo.set_step`: a plain JSONB column does not track in-place
            # writes. Not inside `resolve_llm`, because that is swappable through
            # ctx["llm_resolver"] -- a gate hidden in there is a gate the tests replace.
            if not active_task.progress_json.get("trial_claimed"):
                await consume_trial_run(session, settings, user_id)
                active_task.progress_json = {
                    **active_task.progress_json,
                    "trial_claimed": True,
                }
                await session.commit()

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
                async with _PDF_RENDER_LOCK:
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
            # A ProviderAuthError carries the SDK's own message, which is the right thing to show
            # someone debugging THEIR key and the wrong thing entirely when the key is the
            # deployment's: it is the maintainer's provider account talking -- billing state,
            # quota, project names. The owner saw his own OpenRouter credit balance this way; an
            # invited user would have seen the same sentence about an account they cannot see, act
            # on, or top up. Keep the detail in the task row for the operator; tell the user the one
            # thing that is both true and theirs to act on.
            if isinstance(exc, ProviderAuthError) and await on_deployment_key(
                session, settings, user_id
            ):
                reportable = SHARED_KEY_REJECTED_MESSAGE
            detail = reportable if isinstance(exc, SETUP_ERRORS) else f"{type(exc).__name__}: {exc}"
            if failed_tid is not None:
                failed_task = await session.get(Task, failed_tid)
                if failed_task is not None:
                    task_repo.mark_failed(failed_task, redact(detail, *secrets))
                    await session.commit()
            await bus.publish(channel, {"event": "error", "message": redact(reportable, *secrets)})


async def render_package_pdf(ctx: dict[str, Any], package_id: str) -> None:
    """Render the PDF for an already-persisted package's DOCX, off the API's request path.

    Serialised process-wide via `_PDF_RENDER_LOCK`: two concurrent LibreOffice invocations cost
    ~200-300MB each on top of the worker's ~1.87GB resident set, and max_jobs=2 means two PDF
    renders are otherwise reachable at once -- an OOM the box can already hit with one user and
    two queued packages (architecture.md §2.1).

    Reads the row, closes that transaction, *then* queues on the lock: a render that loses the
    lock race must not sit holding an idle-in-transaction connection for however long the other
    render's LibreOffice subprocess takes (I2) -- the same reason `tailor_job` already commits
    `persist_package` before touching LibreOffice (see the note below).
    """
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    storage: PackageStorage = ctx["storage"]
    async with factory() as session:
        row = await session.get(Package, uuid.UUID(package_id))
        if row is None or row.docx_path is None:
            return
        # Nothing to write yet -- just releases the connection before the (possibly long) wait
        # on _PDF_RENDER_LOCK below.
        await session.commit()
    async with _PDF_RENDER_LOCK:
        pdf = await asyncio.to_thread(storage.render_pdf, package_id, ctx["soffice_binary"])
    if pdf is not None:
        async with factory() as session:
            row = await session.get(Package, uuid.UUID(package_id))
            if row is not None:
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


def _discovery_channel(user_id: uuid.UUID) -> str:
    """Per-user discovery channel. Nothing subscribes to the bare `DISCOVERY_CHANNEL` today (the
    only SSE endpoint is the task-scoped `task_channel`), but publishing an unscoped `new_jobs`
    count is a live leak waiting for its first subscriber -- the first "new jobs" toast built
    against this channel would show user A's counts to user B (T1)."""
    return f"{DISCOVERY_CHANNEL}:{user_id}"


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

            async with with_user_poll_lock(ctx["engine"], active.user_id) as acquired:
                if not acquired:
                    task_repo.mark_failed(active, "a poll is already running for this account")
                    await session.commit()
                    await bus.publish(
                        channel, {"event": "error", "message": "a poll is already running"}
                    )
                    return
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
                _discovery_channel(active.user_id),
                {"event": "discovery", "new_jobs": summary.new_jobs},
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


async def poll_user(ctx: dict[str, Any], user_id: str) -> None:
    """One user's scheduled poll, its own 600s job_timeout, advisory-locked against a concurrent
    poll_now for the same user."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    engine: AsyncEngine = ctx["engine"]
    bus: EventBus = ctx["event_bus"]
    uid = uuid.UUID(user_id)
    async with with_user_poll_lock(engine, uid) as acquired:
        if not acquired:
            logger.info(
                "skipping scheduled poll for user %s: a poll is already in progress", user_id
            )
            return
        try:
            async with factory() as session:
                summary = await poll_sources(
                    session,
                    uid,
                    http=ctx["discovery_http"],
                    embedder=ctx["embedder"],
                    fernet=_poll_fernet(),
                )
            await bus.publish(
                _discovery_channel(uid), {"event": "discovery", "new_jobs": summary.new_jobs}
            )
        except Exception:
            logger.exception("scheduled poll failed for user %s", user_id)


async def poll_all_sources(ctx: dict[str, Any]) -> None:
    """Cron entry point: enqueue one poll_user job per user and return immediately, so a slow or
    stuck poll for one user never holds another user's poll behind it inside a single 600s task
    (architecture.md §2.3 -- two users used to exceed job_timeout in the old inline loop).

    Staggered one minute apart (`_defer_by`), not all enqueued to run at once: `max_jobs=2` bounds
    peak memory regardless of how many `poll_user` jobs are queued, but with no stagger N of them
    can still occupy *both* worker slots back to back for up to `job_timeout=600`s each, starving a
    user's hand-pressed "Poll now", `tailor_job` or `render_package_pdf` behind the whole fan-out
    (I5) -- exactly the interactive-latency regression this task must not trade for the isolation
    it is adding. One minute is comfortably shorter than the shortest configured poll interval and
    long enough that a poll which finishes quickly (the common case: most cycles find nothing new)
    has freed its slot before the next user's job is even runnable.
    """
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with factory() as session:
        user_ids = await list_user_ids(session)
    for i, user_id in enumerate(user_ids):
        try:
            await ctx["redis"].enqueue_job(
                "poll_user", user_id=str(user_id), _defer_by=timedelta(minutes=i)
            )
        except Exception:
            # A transient Redis error enqueueing user 3 of N must not silently drop 4..N for the
            # whole cycle (I1) -- the old inline loop's per-user try/except covered this; the
            # dispatcher needs its own, since arq only retries a job that is already running, never
            # a failed enqueue_job call.
            logger.exception("could not enqueue the scheduled poll for user %s", user_id)


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
    """Rescore every job for one user. Runs for one user never overlap (A1) and none is dropped:
    a run that finds the lock held re-enqueues itself 30 s later instead of waiting. A re-run
    recomputes from the then-current tracks, so a role saved during the first run is scored by the
    next one. Deliberately no arq `_job_id` -- see `with_user_rescore_lock` and the plan."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    try:
        uid = uuid.UUID(user_id)
        async with with_user_rescore_lock(ctx["engine"], uid) as acquired:
            if not acquired:
                await ctx["redis"].enqueue_job(
                    "rescore_jobs", user_id=user_id, _defer_by=RESCORE_REQUEUE_DELAY
                )
                logger.info("rescore for user %s deferred: another rescore is running", user_id)
                return
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
    "poll_user": poll_user,
    "score_jobs": score_jobs,
    "rescore_jobs": rescore_jobs,
}
