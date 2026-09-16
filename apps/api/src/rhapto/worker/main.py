from __future__ import annotations

import asyncio
import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.config import get_settings
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.embeddings import FastEmbedProvider
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.eventbus import RedisEventBus
from rhapto.services.llm import warn_if_fake_llm
from rhapto.services.scoring import users_needing_location_backfill
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import (
    embed_blocks,
    poll_all_sources,
    poll_now,
    render_package_pdf,
    rescore_jobs,
    score_jobs,
    tailor_job,
)

logger = logging.getLogger("rhapto.worker")


def cron_hours(interval_hours: int) -> set[int]:
    """Hours of the day (0-23) at which the poll cron should fire, evenly spaced by the interval."""
    if interval_hours <= 0:
        return set()
    return set(range(0, 24, min(interval_hours, 24)))


_location_backfill_done = False


async def enqueue_location_backfill(ctx: dict[str, Any]) -> int:
    """One-shot: re-score every user still holding jobs from before location priority shipped.

    Migration 0005 leaves `jobs.location_tier` NULL on existing rows, and their `best_fit` was
    never multiplied, so they out-rank newly scored jobs until some unrelated edit happens to
    enqueue a rescore. Guarded by a module flag so a restarted event loop in the same process
    cannot queue the work twice, and never allowed to fail startup: a worker that cannot reach
    the queue yet still has to come up and serve.
    """
    global _location_backfill_done
    if _location_backfill_done:
        return 0
    _location_backfill_done = True
    try:
        factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
        async with factory() as session:
            user_ids = await users_needing_location_backfill(session)
        for user_id in user_ids:
            # A slow or unreachable queue must not hold the worker's startup hostage.
            await asyncio.wait_for(
                ctx["redis"].enqueue_job("rescore_jobs", user_id=str(user_id)), timeout=10
            )
        if user_ids:
            logger.info("location backfill: queued a rescore for %d user(s)", len(user_ids))
        return len(user_ids)
    except Exception:
        logger.exception("could not queue the location backfill; jobs keep their old scores")
        return 0


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    warn_if_fake_llm(settings)
    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    # No ctx["llm"]: tailor_job resolves the provider per task, from the task owner's settings.
    ctx["embedder"] = FastEmbedProvider(settings.rhapto_embedding_model)
    ctx["event_bus"] = RedisEventBus(settings.redis_url)
    ctx["storage"] = PackageStorage(settings.rhapto_packages_dir)
    ctx["soffice_binary"] = settings.rhapto_soffice_binary
    ctx["discovery_http"] = DiscoveryHttp(user_agent=settings.rhapto_discovery_user_agent)
    await enqueue_location_backfill(ctx)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    await ctx["event_bus"].close()
    await ctx["discovery_http"].aclose()


_HOURS = cron_hours(get_settings().rhapto_poll_interval_hours)


class WorkerSettings:
    functions = [tailor_job, embed_blocks, render_package_pdf, poll_now, score_jobs, rescore_jobs]
    cron_jobs = (
        [cron(poll_all_sources, hour=_HOURS, minute=0, run_at_startup=False)] if _HOURS else []
    )
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 600
