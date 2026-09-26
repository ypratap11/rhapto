from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto import __version__
from rhapto.api.auth import is_allowed_email
from rhapto.api.deps import AppState, LlmFactory
from rhapto.api.errors import install_error_handlers
from rhapto.api.routers import (
    applications,
    dashboard,
    discovery,
    jobs,
    meta,
    packages,
    profile,
    search,
    searches,
    tailor,
    taxonomy,
)
from rhapto.api.routers import settings as settings_router
from rhapto.config import Settings, get_settings
from rhapto.db.models import User
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.registry import build_llm
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.enqueue import ArqEnqueuer, Enqueuer
from rhapto.services.eventbus import EventBus, RedisEventBus
from rhapto.services.jobtext import FetchText, fetch_job_text
from rhapto.services.llm import warn_if_fake_llm
from rhapto.services.storage import PackageStorage

API_PREFIX = "/api/v1"


async def _any_allowed_user_exists(session: AsyncSession, settings: Settings) -> bool:
    emails = await session.scalars(select(User.email))
    return any(
        is_allowed_email(e, settings.rhapto_allowed_emails, settings.rhapto_allowed_email_domains)
        for e in emails
    )


def create_app(
    settings: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    enqueuer: Enqueuer | None = None,
    event_bus: EventBus | None = None,
    storage: PackageStorage | None = None,
    fetch_text: FetchText | None = None,
    llm_factory: LlmFactory | None = None,
    discovery_http: DiscoveryHttp | None = None,
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
        llm_factory=llm_factory or build_llm,
        discovery_http=discovery_http
        or DiscoveryHttp(
            user_agent=settings.rhapto_discovery_user_agent,
            base_override=settings.rhapto_discovery_base_override,
        ),
        engine=engine,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        warn_if_fake_llm(settings)
        if settings.rhapto_auth_mode == "access":
            if not settings.rhapto_access_team or not settings.rhapto_access_aud:
                raise RuntimeError(
                    "RHAPTO_AUTH_MODE=access requires RHAPTO_ACCESS_TEAM and RHAPTO_ACCESS_AUD to "
                    "both be set; refusing to start with either empty, since every request would "
                    "otherwise fail with no actionable error (503 from an unreachable JWKS host, or "
                    "401 from an audience check that can never pass)."
                )
            async with state.session_factory() as session:
                allowed = await _any_allowed_user_exists(session, settings)
            if not allowed:
                raise RuntimeError(
                    "RHAPTO_AUTH_MODE=access but no users row matches RHAPTO_ALLOWED_EMAILS/"
                    "RHAPTO_ALLOWED_EMAIL_DOMAINS. Refusing to start: this is the failure mode "
                    "that makes the owner's existing account appear to have vanished. Run "
                    "`rhapto accounts set-email <old> <new>` first if RHAPTO_USER_EMAIL does not "
                    "match the owner's Cloudflare Access email."
                )
        else:
            async with state.session_factory() as session:
                user = await get_or_create_user(session, settings.rhapto_user_email)
                await session.commit()
                state.user_id = user.id
        try:
            yield
        finally:
            # The arq pool and the redis pub/sub client own connections; the in-memory test
            # doubles have nothing to close.
            for collaborator in (state.enqueuer, state.event_bus):
                close = getattr(collaborator, "close", None)
                if close is not None:
                    await close()
            await state.discovery_http.aclose()
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
    # In access mode the browser talks to this API only through the Next.js same-origin proxy
    # (apps/web/src/app/api/v1/[...path]/route.ts), so there is no cross-origin request to allow;
    # installing CORS anyway would just be a wider door than access mode's threat model wants. In
    # token mode the web app and API are genuinely different origins (localhost:3000/8000, or a
    # self-hoster's own split), so CORS stays exactly as it was.
    if settings.rhapto_auth_mode == "token":
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
    app.include_router(discovery.router, prefix=API_PREFIX, tags=["discovery"])
    app.include_router(tailor.router, prefix=API_PREFIX, tags=["tailor"])
    app.include_router(packages.router, prefix=API_PREFIX, tags=["packages"])
    app.include_router(applications.router, prefix=API_PREFIX, tags=["applications"])
    app.include_router(settings_router.router, prefix=API_PREFIX, tags=["settings"])
    app.include_router(searches.router, prefix=API_PREFIX, tags=["searches"])
    app.include_router(taxonomy.router, prefix=API_PREFIX, tags=["taxonomy"])
    app.include_router(search.router, prefix=API_PREFIX, tags=["search"])
    app.include_router(dashboard.router, prefix=API_PREFIX, tags=["dashboard"])
    return app


app = create_app(get_settings())
