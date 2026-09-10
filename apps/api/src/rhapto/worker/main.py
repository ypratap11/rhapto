from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from rhapto.config import get_settings
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import FastEmbedProvider
from rhapto.services.eventbus import RedisEventBus
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import embed_blocks, render_package_pdf, tailor_job


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    ctx["llm"] = AnthropicProvider(
        model=settings.rhapto_llm_model, api_key=settings.anthropic_api_key
    )
    ctx["embedder"] = FastEmbedProvider(settings.rhapto_embedding_model)
    ctx["event_bus"] = RedisEventBus(settings.redis_url)
    ctx["storage"] = PackageStorage(settings.rhapto_packages_dir)
    ctx["soffice_binary"] = settings.rhapto_soffice_binary


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    await ctx["event_bus"].close()


class WorkerSettings:
    functions = [tailor_job, embed_blocks, render_package_pdf]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 600
