from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, is_allowed_email, resolve_principal
from rhapto.config import Settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.registry import build_llm
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.enqueue import Enqueuer
from rhapto.services.eventbus import EventBus
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage

# (provider, model, api_key) -> adapter. Injectable so the "test this key" endpoint can be
# exercised without an SDK client or a real key.
LlmFactory = Callable[[str, str, str], LLMProvider]


@dataclass
class AppState:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    enqueuer: Enqueuer
    event_bus: EventBus
    storage: PackageStorage
    fetch_text: FetchText
    discovery_http: DiscoveryHttp
    llm_factory: LlmFactory = build_llm
    user_id: uuid.UUID | None = None
    engine: AsyncEngine | None = None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.rhapto
    return state


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_state(request).session_factory() as session:
        yield session


def get_settings_dep(request: Request) -> Settings:
    return get_state(request).settings


def get_enqueuer(request: Request) -> Enqueuer:
    return get_state(request).enqueuer


def get_event_bus(request: Request) -> EventBus:
    return get_state(request).event_bus


def get_storage(request: Request) -> PackageStorage:
    return get_state(request).storage


def get_fetch_text(request: Request) -> FetchText:
    return get_state(request).fetch_text


def get_llm_factory(request: Request) -> LlmFactory:
    return get_state(request).llm_factory


async def current_user(
    request: Request,
    principal: Annotated[Principal, Depends(resolve_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> uuid.UUID:
    state = get_state(request)
    if principal.mode == "token":
        if state.user_id is None:
            # The lifespan bootstraps the user row; a request that beats it is a readiness
            # problem, not an auth problem.
            raise HTTPException(status_code=503, detail="server not ready")
        return state.user_id
    # access mode: the allowlist is the only gate (architecture.md §1.6 amendment -- the
    # Cloudflare Access policy itself performs authentication only). This is deliberately the
    # *only* thing this branch does -- no seeding, no backfill; Task 5 adds a separate, dedicated
    # endpoint for that (plan-review C6: every endpoint depends on current_user, so it must stay
    # fast and its failure must never look like an auth failure).
    settings = state.settings
    if not is_allowed_email(
        principal.email, settings.rhapto_allowed_emails, settings.rhapto_allowed_email_domains
    ):
        raise HTTPException(status_code=403, detail="this instance is invite-only")
    user = await get_or_create_user(session, principal.email)
    # Record the verified IdP subject the first time it's seen (migration 0011 added
    # `users.idp_subject` specifically for this). Only ever set when currently NULL, never
    # overwritten: the column is UNIQUE, and Access can reissue a `sub` for the same person, so an
    # unconditional write on every request risks colliding with a stale value left on another row.
    if principal.subject and not user.idp_subject:
        user.idp_subject = principal.subject
    await session.commit()
    return user.id
