from __future__ import annotations

import dataclasses
import inspect
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import AdminAction, FeedbackRow, FreeSpend, Task, User
from rhapto.db.repositories import admin
from rhapto.db.repositories.admin import (
    duplicate_groups,
    failed_errors_today,
    list_actions,
    overview_counts,
    search_users,
    user_detail,
)

NOW = datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
TODAY = datetime(2026, 11, 9, tzinfo=UTC)
MARKER = "Wants more resumes"


def _cat(error: str | None) -> str:
    return "other" if error is None else f"cat:{error[:3]}"


async def _user(
    s: AsyncSession,
    email: str,
    *,
    created: datetime | None = None,
    runs: int = 0,
    **kw: Any,
) -> User:
    u = User(email=email, trial_runs_used=runs, **kw)
    if created is not None:
        u.created_at = created
    s.add(u)
    await s.flush()
    return u


async def _task(
    s: AsyncSession,
    user: User,
    *,
    type: str = "tailor_job",
    status: str = "failed",
    created: datetime = NOW - timedelta(hours=1),
    finished: datetime | None = None,
    error: str | None = None,
    progress: dict[str, Any] | None = None,
) -> Task:
    t = Task(
        user_id=user.id,
        type=type,
        status=status,
        error=error,
        progress_json=progress or {},
        created_at=created,
        finished_at=finished if finished is not None else (created if status == "failed" else None),
    )
    s.add(t)
    await s.flush()
    return t


async def _feedback(s: AsyncSession, user: User, text: str, form: str = "quick") -> None:
    s.add(
        FeedbackRow(
            user_id=user.id,
            form=form,
            page_area="jobs" if form == "quick" else None,
            schema_version=1,
            answers={"kind": "idea", "text": text},
            app_version="t",
        )
    )
    await s.flush()


async def _counts(s: AsyncSession, limit: int | None = 3) -> Any:
    return await overview_counts(s, now=NOW, runs_limit=limit, want_more_marker=MARKER)


# ---------------------------------------------------------------- overview


async def test_signups_today_uses_utc_boundary(session: AsyncSession) -> None:
    await _user(session, "a@x.com", created=TODAY - timedelta(minutes=1))
    await _user(session, "b@x.com", created=TODAY)
    await _user(session, "c@x.com", created=TODAY + timedelta(hours=12))
    c = await _counts(session)
    assert c.signups_today == 2
    assert c.signups_total == 3
    assert c.accounts == 3


async def test_failed_counts_use_tailor_job_failed_only(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com")
    await _task(session, u, finished=TODAY + timedelta(hours=1))
    await _task(session, u, finished=TODAY - timedelta(days=2))
    await _task(session, u, finished=TODAY - timedelta(days=9))  # outside both windows
    await _task(session, u, type="poll_now", finished=TODAY + timedelta(hours=1))
    await _task(session, u, status="succeeded", created=NOW - timedelta(hours=2))
    await _task(session, u, status="running", created=NOW - timedelta(hours=2))
    c = await _counts(session)
    assert c.failed_today == 1
    assert c.failed_7d == 2
    assert c.failed_prior_7d == 1  # [today-7d, today): only the one two days back


async def test_alert_inputs_spend_72h_is_exactly_the_window(session: AsyncSession) -> None:
    for hours, cost in ((71, "0.40"), (73, "9.00")):
        session.add(
            FreeSpend(
                user_id=uuid.uuid4(),
                model="m",
                cost_usd=Decimal(cost),
                created_at=NOW - timedelta(hours=hours),
            )
        )
    await session.flush()
    c = await _counts(session)
    assert c.spend_72h == Decimal("0.40")
    # the injected now, not SQL now(): both rows are in November 2026
    assert c.month_spend == Decimal("9.40")


async def test_month_spend_uses_injected_now(session: AsyncSession) -> None:
    last_month = TODAY - timedelta(days=9, hours=1)
    session.add(
        FreeSpend(user_id=uuid.uuid4(), model="m", cost_usd=Decimal("1"), created_at=last_month)
    )
    session.add(FreeSpend(user_id=uuid.uuid4(), model="m", cost_usd=Decimal("2"), created_at=NOW))
    await session.flush()
    assert (await _counts(session)).month_spend == Decimal("2")


async def test_want_more_counts_distinct_users_not_rows(session: AsyncSession) -> None:
    a = await _user(session, "a@x.com")
    b = await _user(session, "b@x.com")
    await _feedback(session, a, MARKER + " after the free runs")
    await _feedback(session, a, MARKER + " again")
    await _feedback(session, b, "I think it says Wants more resumes somewhere")
    assert (await _counts(session)).want_more_users == 1


async def test_want_more_ignores_survey_form(session: AsyncSession) -> None:
    a = await _user(session, "a@x.com")
    await _feedback(session, a, MARKER, form="survey")
    assert (await _counts(session)).want_more_users == 0


async def test_ready_to_ask_requires_both_conditions(session: AsyncSession) -> None:
    await _user(session, "a@x.com", runs=3)  # out of runs, never asked
    short = await _user(session, "b@x.com", runs=2)  # asked, runs left
    ready = await _user(session, "c@x.com", runs=3)
    await _feedback(session, short, MARKER)
    assert (await _counts(session)).ready_to_ask == 0
    await _feedback(session, ready, MARKER)
    assert (await _counts(session)).ready_to_ask == 1
    assert (await _counts(session, limit=None)).ready_to_ask == 0


# -------------------------------------------------------------- duplicates


async def test_alert_inputs_duplicates_groups_plus_tags_and_case(session: AsyncSession) -> None:
    await _user(session, "a+1@d.com", runs=1)
    await _user(session, "a+2@d.com", runs=2)
    await _user(session, "A@D.com", runs=3)
    await _user(session, "other@d.com", runs=9)
    groups = await duplicate_groups(session)
    assert [(g.count, g.runs_used) for g in groups] == [(3, 6)]


async def test_alert_inputs_duplicates_keep_gmail_dots(session: AsyncSession) -> None:
    await _user(session, "a.b@gmail.com")
    await _user(session, "ab@gmail.com")
    assert await duplicate_groups(session) == []


async def test_alert_inputs_duplicates_exclude_empty_local_part(session: AsyncSession) -> None:
    await _user(session, "+x@d.com")
    await _user(session, "+y@d.com")
    assert await duplicate_groups(session) == []


async def test_non_ascii_address_does_not_error(session: AsyncSession) -> None:
    await _user(session, "ÉMILE@example.com")
    await _user(session, "émile@example.com")
    await duplicate_groups(session)
    page = await search_users(session, q="émile", offset=0, now=NOW)
    assert isinstance(page.rows, list)


# ------------------------------------------------------------------ search


async def test_percent_and_underscore_are_literals(session: AsyncSession) -> None:
    lit = await _user(session, "100%_x@example.com")
    await _user(session, "100abx@example.com")
    await _user(session, "plain@example.com")
    page = await search_users(session, q="100%_x", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [lit.id]
    page = await search_users(session, q="%", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [lit.id]
    page = await search_users(session, q="_", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [lit.id]
    bs = await _user(session, "back\\slash@example.com")
    page = await search_users(session, q="\\", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [bs.id]


async def test_empty_q_lists_everyone_newest_first(session: AsyncSession) -> None:
    old = await _user(session, "old@x.com", created=NOW - timedelta(days=2))
    new = await _user(session, "new@x.com", created=NOW - timedelta(days=1))
    page = await search_users(session, q="", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [new.id, old.id]
    assert page.next_offset is None


async def test_search_is_case_insensitive_substring(session: AsyncSession) -> None:
    u = await _user(session, "Jane.Doe@Example.com")
    page = await search_users(session, q="jane.d", offset=0, now=NOW)
    assert [r.id for r in page.rows] == [u.id]


async def test_page_of_25_then_next_offset_none_at_exact_multiple(session: AsyncSession) -> None:
    for i in range(50):
        await _user(session, f"u{i:02d}@x.com", created=NOW - timedelta(minutes=i))
    p1 = await search_users(session, q="", offset=0, now=NOW)
    assert len(p1.rows) == 25 and p1.next_offset == 25
    p2 = await search_users(session, q="", offset=25, now=NOW)
    assert len(p2.rows) == 25 and p2.next_offset is None
    assert not {r.id for r in p1.rows} & {r.id for r in p2.rows}


async def test_failed_count_query_is_one_extra_query_not_per_row(
    session: AsyncSession, select_counter: list[str]
) -> None:
    users = [await _user(session, f"u{i}@x.com") for i in range(5)]
    for u in users:
        await _task(session, u, finished=NOW - timedelta(hours=1))
    await session.commit()
    select_counter.clear()
    page = await search_users(session, q="", offset=0, now=NOW)
    assert len(select_counter) == 2, select_counter
    assert {r.failed_count for r in page.rows} == {1}


async def test_search_never_selects_answers_or_error(
    session: AsyncSession, select_counter: list[str]
) -> None:
    u = await _user(session, "a@x.com")
    await _task(session, u, error="SECRET-SENTINEL")
    await session.commit()
    select_counter.clear()
    page = await search_users(session, q="a@", offset=0, now=NOW)
    assert page.rows
    joined = " ".join(select_counter).lower()
    assert "answers" not in joined
    assert "tasks.error" not in joined
    assert "llm_settings" not in joined


async def test_search_row_carries_blocked_and_runs(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com", runs=2, blocked_at=NOW)
    page = await search_users(session, q="", offset=0, now=NOW)
    assert page.rows[0].runs_used == 2
    assert page.rows[0].blocked_at == NOW
    assert page.rows[0].id == u.id


# ------------------------------------------------------------------ detail


async def _detail(s: AsyncSession, u: User, limit: int | None = 3) -> Any:
    return await user_detail(
        s, u.id, now=NOW, runs_limit=limit, want_more_marker=MARKER, classify=_cat
    )


async def test_did_not_finish_lists_stale_running_tasks(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com")
    stale_q = await _task(session, u, status="queued", created=NOW - timedelta(minutes=20))
    await _task(session, u, status="queued", created=NOW - timedelta(minutes=5))
    stale_r = await _task(session, u, status="running", created=NOW - timedelta(minutes=16))
    await _task(
        session, u, status="running", created=NOW - timedelta(minutes=15)
    )  # not "more than"
    await _task(session, u, status="succeeded", created=NOW - timedelta(hours=3))
    await _task(session, u, type="poll_now", status="running", created=NOW - timedelta(hours=3))
    d = await _detail(session, u)
    assert d is not None
    assert {f.kind for f in d.failures} == {"did_not_finish"}
    assert sorted(f.when for f in d.failures) == sorted([stale_q.created_at, stale_r.created_at])


async def test_failed_and_stale_rows_are_distinguished_and_expose_no_error(
    session: AsyncSession,
) -> None:
    u = await _user(session, "a@x.com")
    await _task(session, u, error="SENTINEL-TEXT here", finished=NOW - timedelta(hours=1))
    await _task(session, u, status="queued", created=NOW - timedelta(hours=2))
    d = await _detail(session, u)
    assert d is not None
    assert sorted(f.kind for f in d.failures) == ["did_not_finish", "failed"]
    for f in d.failures:
        assert not hasattr(f, "error")
    failed = next(f for f in d.failures if f.kind == "failed")
    assert failed.category == "cat:SEN"
    assert "SENTINEL" not in repr(d)


async def test_suggested_fix_counts_only_claimed_and_caps_at_runs_used(
    session: AsyncSession,
) -> None:
    claimed = {"trial_claimed": True}
    u = await _user(session, "a@x.com", runs=3)
    await _task(session, u, progress=claimed)
    await _task(session, u, progress=claimed)
    await _task(session, u)
    assert (await _detail(session, u)).suggested_reset_runs == 2

    for _ in range(3):
        await _task(session, u, progress=claimed)
    assert (await _detail(session, u)).suggested_reset_runs == 3  # capped at runs used

    u2 = await _user(session, "b@x.com", runs=2)  # runs left
    await _task(session, u2, progress=claimed)
    assert (await _detail(session, u2)).suggested_reset_runs is None

    u3 = await _user(session, "c@x.com", runs=3)  # nothing claimed
    await _task(session, u3)
    assert (await _detail(session, u3)).suggested_reset_runs is None
    assert (await _detail(session, u, limit=None)).suggested_reset_runs is None


async def test_suggested_fix_counts_stale_claimed_tasks(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com", runs=3)
    await _task(
        session,
        u,
        status="running",
        created=NOW - timedelta(minutes=30),
        progress={"trial_claimed": True},
    )
    assert (await _detail(session, u)).suggested_reset_runs == 1


async def test_unknown_user_returns_none(session: AsyncSession) -> None:
    d = await user_detail(
        session, uuid.uuid4(), now=NOW, runs_limit=3, want_more_marker=MARKER, classify=_cat
    )
    assert d is None


async def test_detail_survives_user_with_no_tasks(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com")
    d = await _detail(session, u)
    assert d is not None
    assert d.failures == [] and d.history == []
    assert d.free_spend_usd == Decimal(0)
    assert d.asked_for_more is False
    assert d.suggested_reset_runs is None


async def test_detail_reports_spend_ask_and_history(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com", runs=1)
    session.add(FreeSpend(user_id=u.id, model="m", cost_usd=Decimal("0.5"), created_at=NOW))
    await _feedback(session, u, MARKER + " x")
    for i, act in enumerate(("reset_runs", "block")):
        session.add(
            AdminAction(
                actor_email="o@x.com",
                action=act,
                target_user_id=u.id,
                before_json={"n": i},
                after_json={"n": i + 1},
                created_at=NOW - timedelta(hours=2 - i),
            )
        )
    await session.flush()
    d = await _detail(session, u)
    assert d is not None
    assert d.free_spend_usd == Decimal("0.5")
    assert d.asked_for_more is True
    assert [h.action for h in d.history] == ["block", "reset_runs"]
    assert (await list_actions(session, u.id))[0].action == "block"


async def test_failed_errors_today_returns_categories_not_text(session: AsyncSession) -> None:
    u = await _user(session, "a@x.com")
    await _task(session, u, error="SECRET-ONE", finished=TODAY + timedelta(hours=1))
    await _task(session, u, error="SECRET-TWO", finished=TODAY - timedelta(hours=1))
    await _task(session, u, error=None, finished=TODAY + timedelta(hours=2))
    got = await failed_errors_today(session, now=NOW, classify=_cat)
    assert sorted(got) == ["cat:SEC", "other"]


# -------------------------------------------------------------- structural


def test_repository_exposes_no_update_or_delete_for_audit_rows() -> None:
    names = [n for n, _ in inspect.getmembers(admin, inspect.isfunction)]
    assert names
    for n in names:
        assert "update_action" not in n and "delete_action" not in n, n


def test_failed_run_row_has_no_error_field() -> None:
    assert "error" not in {f.name for f in dataclasses.fields(admin.FailedRunRow)}


async def test_reads_change_no_user_row_and_write_no_audit_row(session: AsyncSession) -> None:
    from sqlalchemy import func, select

    u = await _user(session, "a@x.com", runs=3, blocked_at=NOW)
    await _task(session, u, progress={"trial_claimed": True})
    uid = u.id
    await session.commit()

    def snapshot() -> Any:
        return select(User.trial_runs_used, User.blocked_at, User.last_seen_at, User.email).where(
            User.id == uid
        )

    before = (await session.execute(snapshot())).one()
    await overview_counts(session, now=NOW, runs_limit=3, want_more_marker=MARKER)
    await duplicate_groups(session)
    await failed_errors_today(session, now=NOW, classify=_cat)
    await search_users(session, q="a", offset=0, now=NOW)
    await user_detail(session, uid, now=NOW, runs_limit=3, want_more_marker=MARKER, classify=_cat)
    await list_actions(session, uid)
    await session.commit()
    session.expire_all()
    assert (await session.execute(snapshot())).one() == tuple(before)
    assert await session.scalar(select(func.count()).select_from(AdminAction)) == 0
