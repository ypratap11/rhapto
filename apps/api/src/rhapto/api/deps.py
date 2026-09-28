from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rhapto.api.auth import Principal, is_allowed_email, resolve_principal
from rhapto.config import Settings
from rhapto.db.models import User
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.providers.registry import build_llm
from rhapto.services.accounts import ensure_account
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


async def _record_idp_subject(session: AsyncSession, user_id: uuid.UUID, subject: str) -> None:
    """Best-effort: records the verified IdP subject the first time it's seen, in its own
    savepoint (fix-round N1). Two problems this closes at once:

    1. Sharing this write with the account-creation transaction meant a `sub` collision (two
       different, both-allowlisted emails whose IdP somehow issues the same subject) rolled back
       the *account row itself* along with the write -- a permanent, self-repeating 409 lockout
       for the second person, since every retry hits the same collision. The account row is now
       committed by the caller *before* this runs, so this write can never take it down with it.
    2. "Never overwrite" was enforced only in Python (`if not user.idp_subject`), so two
       concurrent first-sign-in requests that both read a NULL subject could both attempt to
       write it.

    `WHERE idp_subject IS NULL` moves point 2 into SQL, where the race cannot reach it. The
    `begin_nested()` savepoint means a collision on the UNIQUE constraint rolls back only this
    write, not the (already-committed) account row: a colliding subject degrades to "audit field
    not recorded", never to "this person cannot sign in".
    """
    try:
        async with session.begin_nested():
            await session.execute(
                update(User)
                .where(User.id == user_id, User.idp_subject.is_(None))
                .values(idp_subject=subject)
            )
    except IntegrityError:
        pass  # another row already holds this subject; the account itself is unaffected
    await session.commit()


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
    user = await ensure_account(session, principal.email)
    # The account row is committed on its own, before the idp_subject write below is even
    # attempted -- see _record_idp_subject's docstring (N1) for why sharing one transaction
    # between the two turned a rare subject collision into a permanent account lockout.
    await session.commit()
    if principal.subject:
        await _record_idp_subject(session, user.id, principal.subject)
    return user.id
