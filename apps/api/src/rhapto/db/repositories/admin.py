"""Owner-only admin reads and writes. This is the only place cross-user SQL lives, and only the
admin router (`rhapto.api.routers.admin`) may import it; the `admin-reads-are-admin-only`
import-linter contract enforces that.

Nothing here selects `answers`, `tasks.error` or `llm_settings` for a response. `answers` appears
only in a WHERE clause. `tasks.error` is read only to be classified inside this module by a
caller-supplied function (`db` may not import `services`); what leaves is the category string, so
no row type here carries the raw text and a later route cannot pass it through.

Every time boundary is computed in Python from an injected `now` (UTC) and passed as a parameter.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db import models  # noqa: F401
from rhapto.db.models import AdminAction, FeedbackRow, FreeSpend, Task, User

#: A queued or running tailor task older than this is reported as "did not finish" (the worker's
#: own timeout is 600 s).
STALE_AFTER = timedelta(minutes=15)
FAILURE_LIST_LIMIT = 50

Classify = Callable[[str | None], str]


@dataclass(frozen=True)
class OverviewCounts:
    signups_total: int
    signups_today: int
    accounts: int
    want_more_users: int
    ready_to_ask: int
    failed_7d: int
    failed_today: int
    failed_prior_7d: int
    spend_72h: Decimal
    month_spend: Decimal


@dataclass(frozen=True)
class DuplicateRow:
    count: int
    runs_used: int


@dataclass(frozen=True)
class UserRow:
    id: uuid.UUID
    email: str
    runs_used: int
    failed_count: int
    last_seen_at: datetime
    blocked_at: datetime | None


@dataclass(frozen=True)
class UserPage:
    rows: list[UserRow]
    next_offset: int | None


@dataclass(frozen=True)
class FailedRunRow:
    when: datetime
    type: str
    category: str
    kind: Literal["failed", "did_not_finish"]


@dataclass(frozen=True)
class AdminActionRow:
    when: datetime
    actor_email: str
    action: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass(frozen=True)
class UserDetail:
    id: uuid.UUID
    email: str
    created_at: datetime
    runs_used: int
    free_spend_usd: Decimal
    asked_for_more: bool
    blocked_at: datetime | None
    failures: list[FailedRunRow]
    suggested_reset_runs: int | None
    history: list[AdminActionRow]


def _utc(now: datetime) -> datetime:
    return now.astimezone(UTC)


def _day_start(now: datetime) -> datetime:
    n = _utc(now)
    return datetime(n.year, n.month, n.day, tzinfo=UTC)


def _month_start(now: datetime) -> datetime:
    n = _utc(now)
    return datetime(n.year, n.month, 1, tzinfo=UTC)


def _wants_more(marker: str) -> Any:
    """Predicate on `feedback`: a quick-form row whose text starts with the marker."""
    return and_(
        FeedbackRow.form == "quick",
        FeedbackRow.answers["text"].astext.startswith(marker, autoescape=True),
    )


def _is_failed_tailor() -> Any:
    return and_(Task.type == "tailor_job", Task.status == "failed")


def _is_stale_tailor(now: datetime) -> Any:
    return and_(
        Task.type == "tailor_job",
        Task.status.in_(("queued", "running")),
        Task.created_at < _utc(now) - STALE_AFTER,
    )


async def overview_counts(
    session: AsyncSession, *, now: datetime, runs_limit: int | None, want_more_marker: str
) -> OverviewCounts:
    today = _day_start(now)
    utc_now = _utc(now)
    users_row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(User.created_at >= today),
            ).select_from(User)
        )
    ).one()
    tasks_row = (
        await session.execute(
            select(
                func.count().filter(Task.finished_at >= utc_now - timedelta(days=7)),
                func.count().filter(Task.finished_at >= today),
                func.count().filter(
                    and_(Task.finished_at >= today - timedelta(days=7), Task.finished_at < today)
                ),
            ).where(_is_failed_tailor())
        )
    ).one()
    want_more = await session.scalar(
        select(func.count(func.distinct(FeedbackRow.user_id))).where(_wants_more(want_more_marker))
    )
    ready = 0
    if runs_limit is not None:
        ready = (
            await session.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.trial_runs_used >= runs_limit,
                    select(FeedbackRow.id)
                    .where(FeedbackRow.user_id == User.id, _wants_more(want_more_marker))
                    .exists(),
                )
            )
            or 0
        )
    spend_row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(FreeSpend.cost_usd).filter(
                        FreeSpend.created_at >= utc_now - timedelta(hours=72)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(FreeSpend.cost_usd).filter(FreeSpend.created_at >= _month_start(now)),
                    0,
                ),
            )
        )
    ).one()
    return OverviewCounts(
        signups_total=users_row[0],
        signups_today=users_row[1],
        accounts=users_row[0],
        want_more_users=want_more or 0,
        ready_to_ask=ready,
        failed_7d=tasks_row[0],
        failed_today=tasks_row[1],
        failed_prior_7d=tasks_row[2],
        spend_72h=Decimal(spend_row[0]),
        month_spend=Decimal(spend_row[1]),
    )


async def duplicate_groups(session: AsyncSession, *, limit: int = 20) -> list[DuplicateRow]:
    """Addresses that are the same once `+tag` is dropped from the local part, case-insensitively.

    Gmail dots are kept. `lower()` is ASCII-only in a C-locale database; the admin match elsewhere
    uses Python `casefold`, so non-ASCII addresses may group less eagerly here. Never an error.
    """
    local = func.split_part(func.split_part(User.email, "@", 1), "+", 1)
    key = func.lower(local) + "@" + func.lower(func.split_part(User.email, "@", 2))
    rows = await session.execute(
        select(func.count(), func.coalesce(func.sum(User.trial_runs_used), 0))
        .where(local != "")
        .group_by(key)
        .having(func.count() >= 2)
        .order_by(func.count().desc(), key)
        .limit(limit)
    )
    return [DuplicateRow(count=int(c), runs_used=int(r)) for c, r in rows.all()]


async def failed_errors_today(
    session: AsyncSession, *, now: datetime, classify: Classify, limit: int = 1000
) -> list[str]:
    """Categories (not text) of today's failed tailor runs. Classified here; raw text stays here."""
    rows = await session.execute(
        select(Task.error)
        .where(_is_failed_tailor(), Task.finished_at >= _day_start(now))
        .order_by(Task.finished_at.desc())
        .limit(limit)
    )
    return [classify(e) for (e,) in rows.all()]


def _escape_like(term: str) -> str:
    return term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_users(
    session: AsyncSession, *, q: str, offset: int, now: datetime, page_size: int = 25
) -> UserPage:
    """Users matching `q` (substring of the email, literal), newest first.

    `failed_count` is failed tailor runs in the trailing 7 days, from one extra query.
    """
    stmt: Select[Any] = select(
        User.id, User.email, User.trial_runs_used, User.last_seen_at, User.blocked_at
    )
    term = q.strip()
    if term:
        stmt = stmt.where(User.email.ilike(f"%{_escape_like(term)}%", escape="\\"))
    stmt = stmt.order_by(User.created_at.desc(), User.id).offset(offset).limit(page_size + 1)
    fetched = (await session.execute(stmt)).all()
    page = fetched[:page_size]
    failed: dict[uuid.UUID, int] = {}
    if page:
        counts = await session.execute(
            select(Task.user_id, func.count())
            .where(
                Task.user_id.in_([r.id for r in page]),
                _is_failed_tailor(),
                Task.finished_at >= _utc(now) - timedelta(days=7),
            )
            .group_by(Task.user_id)
        )
        failed = {uid: int(n) for uid, n in counts.all()}
    rows = [
        UserRow(
            id=r.id,
            email=r.email,
            runs_used=r.trial_runs_used,
            failed_count=failed.get(r.id, 0),
            last_seen_at=r.last_seen_at,
            blocked_at=r.blocked_at,
        )
        for r in page
    ]
    return UserPage(rows=rows, next_offset=offset + page_size if len(fetched) > page_size else None)


async def list_actions(session: AsyncSession, user_id: uuid.UUID) -> list[AdminActionRow]:
    rows = await session.execute(
        select(
            AdminAction.created_at,
            AdminAction.actor_email,
            AdminAction.action,
            AdminAction.before_json,
            AdminAction.after_json,
        )
        .where(AdminAction.target_user_id == user_id)
        .order_by(AdminAction.created_at.desc(), AdminAction.id)
    )
    return [
        AdminActionRow(when=w, actor_email=a, action=act, before=b, after=af)
        for w, a, act, b, af in rows.all()
    ]


async def user_detail(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime,
    runs_limit: int | None,
    want_more_marker: str,
    classify: Classify,
) -> UserDetail | None:
    user = (
        await session.execute(
            select(
                User.id, User.email, User.created_at, User.trial_runs_used, User.blocked_at
            ).where(User.id == user_id)
        )
    ).one_or_none()
    if user is None:
        return None
    task_rows = (
        await session.execute(
            select(
                Task.created_at,
                Task.finished_at,
                Task.type,
                Task.status,
                Task.error,
            )
            .where(Task.user_id == user_id, or_(_is_failed_tailor(), _is_stale_tailor(now)))
            .order_by(func.coalesce(Task.finished_at, Task.created_at).desc(), Task.id)
            .limit(FAILURE_LIST_LIMIT)
        )
    ).all()
    failures = [
        FailedRunRow(
            when=t.finished_at or t.created_at,
            type=t.type,
            category=classify(t.error),
            kind="failed" if t.status == "failed" else "did_not_finish",
        )
        for t in task_rows
    ]
    claimed = (
        await session.scalar(
            select(func.count()).where(
                Task.user_id == user_id,
                or_(_is_failed_tailor(), _is_stale_tailor(now)),
                Task.progress_json["trial_claimed"].astext == "true",
            )
        )
        or 0
    )
    suggested: int | None = None
    capped = min(int(claimed), user.trial_runs_used)
    if capped > 0 and runs_limit is not None and user.trial_runs_used >= runs_limit:
        suggested = capped
    spend = await session.scalar(
        select(func.coalesce(func.sum(FreeSpend.cost_usd), 0)).where(FreeSpend.user_id == user_id)
    )
    asked = await session.scalar(
        select(
            select(FeedbackRow.id)
            .where(FeedbackRow.user_id == user_id, _wants_more(want_more_marker))
            .exists()
        )
    )
    return UserDetail(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        runs_used=user.trial_runs_used,
        free_spend_usd=Decimal(spend or 0),
        asked_for_more=bool(asked),
        blocked_at=user.blocked_at,
        failures=failures,
        suggested_reset_runs=suggested,
        history=await list_actions(session, user_id),
    )


# ---------------------------------------------------------------------------------------------
# Audited writes. Each takes FOR NO KEY UPDATE on the user row (which does not conflict with the
# FOR KEY SHARE that FK checks take), changes the row, inserts the audit row and commits once, so
# the action and its record stand or fall together.
# ---------------------------------------------------------------------------------------------


class UserNotFound(Exception):
    """No such user (maps to 404)."""


class ResetWouldRaise(Exception):
    """The requested value is above the current count; a reset only lowers (maps to 409)."""


class ProtectedAccount(Exception):
    """An admin address cannot be blocked (maps to 409)."""


@dataclass(frozen=True)
class ResetResult:
    changed: bool
    before: int
    after: int


@dataclass(frozen=True)
class BlockResult:
    changed: bool
    blocked_at: datetime | None


def _audit(
    session: AsyncSession,
    *,
    actor_email: str,
    action: str,
    user_id: uuid.UUID,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    session.add(
        AdminAction(
            actor_email=actor_email,
            action=action,
            target_user_id=user_id,
            before_json=before,
            after_json=after,
        )
    )


async def reset_runs(
    session: AsyncSession, *, actor_email: str, user_id: uuid.UUID, to: int
) -> ResetResult:
    """Lower `trial_runs_used` to `to` (0..current). Never raises it; never refunds automatically."""
    if to < 0:
        raise ValueError("to must be >= 0")
    try:
        current = await session.scalar(
            select(User.trial_runs_used)
            .where(User.id == user_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise UserNotFound(str(user_id))
        if to > current:
            raise ResetWouldRaise(f"{to} > {current}")
        if to == current:
            await session.rollback()
            return ResetResult(changed=False, before=current, after=current)
        await session.execute(
            update(User)
            .where(User.id == user_id, User.trial_runs_used >= to)
            .values(trial_runs_used=to)
        )
        _audit(
            session,
            actor_email=actor_email,
            action="reset_runs",
            user_id=user_id,
            before={"trial_runs_used": current},
            after={"trial_runs_used": to},
        )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return ResetResult(changed=True, before=current, after=to)


async def set_blocked(
    session: AsyncSession,
    *,
    actor_email: str,
    user_id: uuid.UUID,
    blocked: bool,
    protected: bool,
) -> BlockResult:
    """Block or unblock an account. A protected account can be unblocked but never blocked."""
    if blocked and protected:
        raise ProtectedAccount(str(user_id))
    try:
        row = (
            await session.execute(
                select(User.id, User.blocked_at)
                .where(User.id == user_id)
                .with_for_update(key_share=True)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise UserNotFound(str(user_id))
        was_blocked = row.blocked_at is not None
        if was_blocked == blocked:
            await session.rollback()
            return BlockResult(changed=False, blocked_at=row.blocked_at)
        new_at = (
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(blocked_at=func.now() if blocked else None)
                .returning(User.blocked_at)
            )
        ).scalar_one()
        _audit(
            session,
            actor_email=actor_email,
            action="block" if blocked else "unblock",
            user_id=user_id,
            before={"blocked": was_blocked},
            after={"blocked": blocked},
        )
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return BlockResult(changed=True, blocked_at=new_at)
