from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from rhapto.config import get_settings
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import FastEmbedProvider
from rhapto.engine.providers.registry import PROVIDERS
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.eventbus import RedisEventBus
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


def cron_hours(interval_hours: int) -> set[int]:
    """Hours of the day (0-23) at which the poll cron should fire, evenly spaced by the interval."""
    if interval_hours <= 0:
        return set()
    return set(range(0, 24, min(interval_hours, 24)))


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    ctx["llm"] = AnthropicProvider(
        model=settings.rhapto_llm_model or PROVIDERS["anthropic"].default,
        api_key=settings.anthropic_api_key,
    )
    ctx["embedder"] = FastEmbedProvider(settings.rhapto_embedding_model)
    ctx["event_bus"] = RedisEventBus(settings.redis_url)
    ctx["storage"] = PackageStorage(settings.rhapto_packages_dir)
    ctx["soffice_binary"] = settings.rhapto_soffice_binary
    ctx["discovery_http"] = DiscoveryHttp(user_agent=settings.rhapto_discovery_user_agent)


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
