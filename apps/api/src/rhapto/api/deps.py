from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, resolve_principal
from rhapto.config import Settings
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
) -> uuid.UUID:
    state = get_state(request)
    if principal.mode == "token":
        if state.user_id is None:
            # The lifespan bootstraps the user row; a request that beats it is a readiness
            # problem, not an auth problem.
            raise HTTPException(status_code=503, detail="server not ready")
        return state.user_id
    # access mode: Task 3 maps principal.email to a users.id (get-or-create on first sign-in).
    raise HTTPException(status_code=501, detail="access mode is not yet supported")
