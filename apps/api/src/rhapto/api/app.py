from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto import __version__
from rhapto.api.deps import AppState
from rhapto.api.errors import install_error_handlers
from rhapto.api.routers import applications, jobs, meta, packages, profile, tailor
from rhapto.config import Settings, get_settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory
from rhapto.services.enqueue import ArqEnqueuer, Enqueuer
from rhapto.services.eventbus import EventBus, RedisEventBus
from rhapto.services.jobtext import FetchText, fetch_job_text
from rhapto.services.storage import PackageStorage

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    enqueuer: Enqueuer | None = None,
    event_bus: EventBus | None = None,
    storage: PackageStorage | None = None,
    fetch_text: FetchText | None = None,
) -> FastAPI:
    engine = None
    if session_factory is None:
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
    state = AppState(
        settings=settings,
        session_factory=session_factory,
        enqueuer=enqueuer or ArqEnqueuer(settings.redis_url),
        event_bus=event_bus or RedisEventBus(settings.redis_url),
        storage=storage or PackageStorage(settings.rhapto_packages_dir),
        fetch_text=fetch_text or fetch_job_text,
        engine=engine,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with state.session_factory() as session:
            user = await get_or_create_user(session, settings.rhapto_user_email)
            await session.commit()
            state.user_id = user.id
        try:
            yield
        finally:
            if state.engine is not None:
                await state.engine.dispose()

    app = FastAPI(
        title="Rhapto API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    app.state.rhapto = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.rhapto_web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    install_error_handlers(app)
    app.include_router(meta.router, prefix=API_PREFIX, tags=["meta"])
    app.include_router(profile.router, prefix=API_PREFIX, tags=["profile"])
    app.include_router(jobs.router, prefix=API_PREFIX, tags=["jobs"])
    app.include_router(tailor.router, prefix=API_PREFIX, tags=["tailor"])
    app.include_router(packages.router, prefix=API_PREFIX, tags=["packages"])
    app.include_router(applications.router, prefix=API_PREFIX, tags=["applications"])
    return app


app = create_app(get_settings())
