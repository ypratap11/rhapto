from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.admin_guard import AdminRoute
from rhapto.api.admin_schemas import (
    ActionOut,
    AdminSessionOut,
    AlertOut,
    FailureOut,
    OverviewOut,
    UserDetailOut,
    UserRowOut,
    UserSearchIn,
    UserSearchOut,
)
from rhapto.api.deps import get_session, get_settings_dep
from rhapto.api.errors import not_found
from rhapto.config import Settings
from rhapto.db.repositories import admin as admin_repo
from rhapto.services import admin_alerts
from rhapto.services.failure_categories import FAILURE_LABELS, FailureCategory, classify
from rhapto.services.trial import configured_trial_limit

logger = logging.getLogger("rhapto.api.admin")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]

router = APIRouter(prefix="/admin", route_class=AdminRoute, include_in_schema=False)


@router.get("/session", response_model=AdminSessionOut)
async def admin_session() -> AdminSessionOut:
    """Reached only when the guard has proven the caller an admin."""
    return AdminSessionOut(ok=True)


def _now() -> datetime:
    return datetime.now(UTC)


def _budget(settings: Settings) -> Decimal | None:
    value = settings.rhapto_monthly_free_budget_usd
    return None if value < 0 else Decimal(str(value))


def _failure(row: admin_repo.FailedRunRow) -> FailureOut:
    # `kind` decides first: a stale queued/running task has no error text to classify.
    category = (
        FailureCategory.did_not_finish
        if row.kind == "did_not_finish"
        else FailureCategory(row.category)
    )
    return FailureOut(
        when=row.when, type=row.type, category=category, label=FAILURE_LABELS[category]
    )


@router.get("/overview", response_model=OverviewOut)
async def admin_overview(session: SessionDep, settings: SettingsDep) -> OverviewOut:
    now = _now()
    limit = configured_trial_limit(settings)
    counts = await admin_repo.overview_counts(
        session, now=now, runs_limit=limit, want_more_marker=admin_alerts.WANT_MORE_MARKER
    )
    budget = _budget(settings)
    dupes = await admin_repo.duplicate_groups(session)
    top: FailureCategory | None = None
    if counts.failed_today:
        cats = await admin_repo.failed_errors_today(session, now=now, classify=classify)
        if cats:
            top = FailureCategory(Counter(cats).most_common(1)[0][0])
    found = [
        admin_alerts.budget_alert(
            spend_72h=counts.spend_72h, month_spend=counts.month_spend, budget=budget, now=now
        ),
        admin_alerts.duplicate_alert(
            [admin_alerts.DuplicateGroup(d.count, d.runs_used) for d in dupes]
        ),
        admin_alerts.failure_spike_alert(
            today=counts.failed_today, prior_7d=counts.failed_prior_7d, top_category=top
        ),
        admin_alerts.ready_to_ask_alert(ready=counts.ready_to_ask, runs_limit=limit),
        admin_alerts.signin_limit_alert(accounts=counts.accounts),
    ]
    return OverviewOut(
        signups_total=counts.signups_total,
        signups_today=counts.signups_today,
        free_spend_month_usd=f"{counts.month_spend:.2f}",
        budget_usd=None if budget is None else float(budget),
        accounts=counts.accounts,
        account_cap=admin_alerts.SIGNIN_CAP,
        want_more_users=counts.want_more_users,
        failed_7d=counts.failed_7d,
        alerts=[
            AlertOut(id=a.id.value, tone=a.tone, title=a.title, detail=a.detail)
            for a in found
            if a is not None
        ],
    )


@router.post("/users/search", response_model=UserSearchOut)
async def admin_user_search(
    body: UserSearchIn, session: SessionDep, settings: SettingsDep
) -> UserSearchOut:
    page = await admin_repo.search_users(session, q=body.q, offset=body.offset, now=_now())
    limit = configured_trial_limit(settings)
    return UserSearchOut(
        users=[
            UserRowOut(
                id=r.id,
                email=r.email,
                runs_used=r.runs_used,
                runs_limit=limit,
                failed_count=r.failed_count,
                last_seen_at=r.last_seen_at,
                blocked=r.blocked_at is not None,
            )
            for r in page.rows
        ],
        next_offset=page.next_offset,
    )


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def admin_user_detail(
    user_id: uuid.UUID, session: SessionDep, settings: SettingsDep
) -> UserDetailOut:
    limit = configured_trial_limit(settings)
    detail = await admin_repo.user_detail(
        session,
        user_id,
        now=_now(),
        runs_limit=limit,
        want_more_marker=admin_alerts.WANT_MORE_MARKER,
        classify=classify,
    )
    if detail is None:
        raise not_found("user", user_id)
    logger.debug("admin user detail user_id=%s", user_id)
    return UserDetailOut(
        id=detail.id,
        email=detail.email,
        joined_at=detail.created_at,
        runs_used=detail.runs_used,
        runs_limit=limit,
        free_spend_usd=f"{detail.free_spend_usd:.2f}",
        asked_for_more=detail.asked_for_more,
        blocked=detail.blocked_at is not None,
        failures=[_failure(f) for f in detail.failures],
        suggested_reset_runs=detail.suggested_reset_runs,
        history=[
            ActionOut(
                when=h.when,
                actor_email=h.actor_email,
                action=h.action,
                before=h.before,
                after=h.after,
            )
            for h in detail.history
        ],
    )


# Real admin routes (Tasks 11 and 12) must be registered ABOVE this call: Starlette takes the first
# full match, so the catch-all has to come last.
_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"]


def _register_catch_all(r: APIRouter) -> None:
    # Every method, so none answers 405 + `Allow` (which would reveal the area to anyone); and the
    # bare `/admin` too, since `/{rest:path}` needs the slash and Starlette would redirect (307)
    # before any guard ran.
    @r.api_route("", methods=_ALL_METHODS, include_in_schema=False)
    @r.api_route("/{rest:path}", methods=_ALL_METHODS, include_in_schema=False)
    async def admin_unknown(rest: str = "") -> None:
        raise HTTPException(status_code=404)


_register_catch_all(router)
