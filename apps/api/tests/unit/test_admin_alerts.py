"""Owner-dashboard alert rules: pure, injected `now`, firing / non-firing / empty data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from rhapto.services import admin_alerts
from rhapto.services.admin_alerts import (
    WANT_MORE_MARKER,
    AlertId,
    DuplicateGroup,
    budget_alert,
    duplicate_alert,
    failure_spike_alert,
    month_bounds,
    ready_to_ask_alert,
    signin_limit_alert,
)
from rhapto.services.failure_categories import FAILURE_LABELS, FailureCategory

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
D = Decimal


def _budget(month: str, spend_72h: str, budget: str | None = "50"):
    return budget_alert(
        spend_72h=D(spend_72h),
        month_spend=D(month),
        budget=None if budget is None else D(budget),
        now=NOW,
    )


def test_budget_fires_with_projected_date() -> None:
    # 20 left at 3/day = 6d16h after 20 Nov 12:00 = 27 Nov 04:00
    alert = _budget("30", "9")
    assert alert is not None
    assert alert.id is AlertId.budget
    assert alert.tone == "warn"
    assert "estimate" in alert.detail
    assert "27 Nov" in alert.detail


def test_budget_fires_just_before_month_end() -> None:
    # 20.9 left at 2/day = 10.45 d = 10d10h48m -> 30 Nov 22:48
    alert = _budget("29.1", "6")
    assert alert is not None
    assert "30 Nov" in alert.detail


def test_budget_does_not_fire_exactly_at_month_end() -> None:
    # 21 left at 2/day = 10.5 d -> exactly 1 Dec 00:00
    assert _budget("29", "6") is None


def test_budget_does_not_fire_just_after_month_end() -> None:
    # 21.1 left at 2/day = 10.55 d -> 1 Dec 01:12
    assert _budget("28.9", "6") is None


def test_budget_does_not_fire_on_slow_pace() -> None:
    # 20 left at 1/day = 20 d -> 10 Dec 12:00
    assert _budget("30", "3") is None


def test_budget_zero_rate_does_not_divide() -> None:
    assert _budget("30", "0") is None


def test_budget_disabled_is_silent() -> None:
    assert _budget("49", "30", budget=None) is None


def test_budget_reached_fires_without_a_date() -> None:
    alert = _budget("50", "0")
    assert alert is not None
    assert "budget reached" in alert.detail.lower()
    assert not re.search(r"\d{1,2} [A-Z][a-z]{2}", alert.detail)


def test_duplicates_fires_naming_counts() -> None:
    alert = duplicate_alert([DuplicateGroup(count=3, runs_used=9)])
    assert alert is not None
    assert alert.id is AlertId.duplicates
    assert "3" in alert.detail
    assert "9" in alert.detail


def test_duplicates_empty_is_silent() -> None:
    assert duplicate_alert([]) is None


@pytest.mark.parametrize(("today", "prior"), [(5, 10), (5, 11), (5, 0)])
def test_failures_fire(today: int, prior: int) -> None:
    alert = failure_spike_alert(today=today, prior_7d=prior, top_category=None)
    assert alert is not None
    assert alert.id is AlertId.failures


@pytest.mark.parametrize(("today", "prior"), [(4, 0), (5, 12), (5, 14), (0, 0)])
def test_failures_do_not_fire(today: int, prior: int) -> None:
    assert failure_spike_alert(today=today, prior_7d=prior, top_category=None) is None


def test_failures_category_sentence_only_when_given() -> None:
    plain = failure_spike_alert(today=5, prior_7d=0, top_category=None)
    with_cat = failure_spike_alert(today=5, prior_7d=0, top_category=FailureCategory.provider_error)
    assert plain is not None and with_cat is not None
    assert FAILURE_LABELS[FailureCategory.provider_error] in with_cat.detail
    assert FAILURE_LABELS[FailureCategory.provider_error] not in plain.detail


def test_ready_fires_with_owner_wording() -> None:
    alert = ready_to_ask_alert(ready=1, runs_limit=3)
    assert alert is not None
    assert alert.id is AlertId.ready_to_ask
    assert alert.tone == "info"
    assert "10 paying or 30 asking" in alert.detail
    seven = ready_to_ask_alert(ready=7, runs_limit=3)
    assert seven is not None
    assert "7" in seven.detail and "30" in seven.detail


def test_ready_silent_at_zero_or_cap_disabled() -> None:
    assert ready_to_ask_alert(ready=0, runs_limit=3) is None
    assert ready_to_ask_alert(ready=5, runs_limit=None) is None


@pytest.mark.parametrize("n", [40, 41, 50])
def test_signin_fires(n: int) -> None:
    alert = signin_limit_alert(accounts=n)
    assert alert is not None
    assert alert.id is AlertId.signin_limit
    assert "estimate" in alert.detail


@pytest.mark.parametrize("n", [39, 0])
def test_signin_silent(n: int) -> None:
    assert signin_limit_alert(accounts=n) is None


def test_month_bounds() -> None:
    assert month_bounds(NOW) == (
        datetime(2026, 11, 1, tzinfo=UTC),
        datetime(2026, 12, 1, tzinfo=UTC),
    )


def test_month_bounds_december_rolls_the_year() -> None:
    start, end = month_bounds(datetime(2026, 12, 15, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


def test_marker_matches_the_web_constant() -> None:
    src = Path(__file__).resolve().parents[4] / "apps/web/src/components/feedback/WantMoreRuns.tsx"
    match = re.search(r'WANT_MORE_RUNS_TEXT\s*=\s*"([^"]*)"', src.read_text(encoding="utf-8"))
    assert match, "WANT_MORE_RUNS_TEXT not found"
    assert match.group(1).startswith(WANT_MORE_MARKER)
    assert admin_alerts.WANT_MORE_MARKER == WANT_MORE_MARKER
