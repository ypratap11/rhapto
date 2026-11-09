"""Deterministic alert rules for the owner's admin dashboard.

Pure functions: no database, no clock (callers inject `now`), no model calls. Money is `Decimal`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from rhapto.services.failure_categories import FAILURE_LABELS, FailureCategory

# The web's WANT_MORE_RUNS_TEXT must start with this; a test reads the .tsx to keep them in step.
WANT_MORE_MARKER = "Wants more resumes"
SIGNIN_CAP = 50
SIGNIN_WARN_AT = 40


class AlertId(StrEnum):
    budget = "budget"
    duplicates = "duplicates"
    failures = "failures"
    ready_to_ask = "ready_to_ask"
    signin_limit = "signin_limit"


@dataclass(frozen=True)
class Alert:
    id: AlertId
    tone: Literal["warn", "info"]
    title: str
    detail: str


@dataclass(frozen=True)
class DuplicateGroup:
    count: int
    runs_used: int


def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    """UTC start of `now`'s month and the start of the next month."""
    utc = now.astimezone(UTC)
    start = datetime(utc.year, utc.month, 1, tzinfo=UTC)
    if utc.month == 12:
        return start, datetime(utc.year + 1, 1, 1, tzinfo=UTC)
    return start, datetime(utc.year, utc.month + 1, 1, tzinfo=UTC)


def budget_alert(
    *, spend_72h: Decimal, month_spend: Decimal, budget: Decimal | None, now: datetime
) -> Alert | None:
    if budget is None:
        return None
    title = "AI spend may hit the monthly budget"
    if month_spend >= budget:
        return Alert(AlertId.budget, "warn", title, "Budget reached for this month.")
    if spend_72h <= 0:
        return None
    # days = remaining / (spend_72h / 3), computed in whole microseconds to stay exact.
    micros = int((budget - month_spend) * 3 * 86_400_000_000 / spend_72h)
    projected = now.astimezone(UTC) + timedelta(microseconds=micros)
    _, next_month = month_bounds(now)
    if projected >= next_month:
        return None
    return Alert(
        AlertId.budget,
        "warn",
        title,
        f"At the last 3 days' pace the budget runs out on {projected.day} "
        f"{projected:%b} (estimate, UTC).",
    )


def duplicate_alert(groups: Sequence[DuplicateGroup]) -> Alert | None:
    if not groups:
        return None
    parts = [f"{g.count} accounts sharing one address ({g.runs_used} runs used)" for g in groups]
    return Alert(
        AlertId.duplicates,
        "warn",
        "Possible duplicate sign-ups",
        "Same address apart from a +tag: " + "; ".join(parts) + ".",
    )


def failure_spike_alert(
    *, today: int, prior_7d: int, top_category: FailureCategory | None
) -> Alert | None:
    if not (today >= 5 and today * 7 >= 3 * prior_7d):
        return None
    detail = f"{today} runs failed today against {prior_7d} in the previous 7 days."
    if top_category is not None:
        detail += f" Most common: {FAILURE_LABELS[top_category]}."
    return Alert(AlertId.failures, "warn", "Failed runs jumped", detail)


def ready_to_ask_alert(*, ready: int, runs_limit: int | None) -> Alert | None:
    if runs_limit is None or ready < 1:
        return None
    return Alert(
        AlertId.ready_to_ask,
        "info",
        "Ready to be asked",
        f"{ready} people used all {runs_limit} free runs and asked for more. "
        "Your trigger is 10 paying or 30 asking.",
    )


def signin_limit_alert(*, accounts: int) -> Alert | None:
    if accounts < SIGNIN_WARN_AT:
        return None
    return Alert(
        AlertId.signin_limit,
        "warn",
        "Sign-in limit approaching",
        f"{accounts} of {SIGNIN_CAP} sign-in accounts used (estimate).",
    )
