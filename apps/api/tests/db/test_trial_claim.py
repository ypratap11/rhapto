"""The trial counter at the SQL level: one conditional UPDATE is the whole mutual exclusion.

These tests are about the claim itself, not the policy that decides whether a cap applies -- that
is `tests/unit/test_trial_policy.py`. The starred cases in the architecture (§8 tests 4 and 5) are
`test_two_concurrent_claims_never_both_take_the_last_run` and
`test_one_users_exhausted_allowance_does_not_touch_another`.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import User
from rhapto.db.repositories.users import claim_trial_run, get_or_create_user, trial_runs_used

LIMIT = 3


async def _set_used(session: AsyncSession, user_id: uuid.UUID, used: int) -> None:
    await session.execute(
        text("UPDATE users SET trial_runs_used = :n WHERE id = :uid"),
        {"n": used, "uid": str(user_id)},
    )
    await session.commit()


async def test_a_fresh_account_has_spent_nothing(session: AsyncSession, user: User) -> None:
    assert await trial_runs_used(session, user.id) == 0


async def test_an_unknown_user_reads_zero_rather_than_raising(session: AsyncSession) -> None:
    """The gate must never turn "no such row" into a 500 on a money path."""
    assert await trial_runs_used(session, uuid.uuid4()) == 0


async def test_claim_increments_and_returns_the_new_count(
    session: AsyncSession, user: User
) -> None:
    assert await claim_trial_run(session, user.id, LIMIT) == 1
    assert await claim_trial_run(session, user.id, LIMIT) == 2
    assert await claim_trial_run(session, user.id, LIMIT) == 3
    await session.commit()
    assert await trial_runs_used(session, user.id) == 3


async def test_a_claim_at_the_limit_returns_none_and_leaves_the_count_alone(
    session: AsyncSession, user: User
) -> None:
    await _set_used(session, user.id, LIMIT)
    assert await claim_trial_run(session, user.id, LIMIT) is None
    await session.commit()
    assert await trial_runs_used(session, user.id) == LIMIT


async def test_a_limit_of_zero_never_claims(session: AsyncSession, user: User) -> None:
    """Zero is a cap, not "disabled": an operator who wants nobody but themselves on their key."""
    assert await claim_trial_run(session, user.id, 0) is None
    await session.commit()
    assert await trial_runs_used(session, user.id) == 0


async def test_a_claim_for_a_missing_row_returns_none(session: AsyncSession) -> None:
    assert await claim_trial_run(session, uuid.uuid4(), LIMIT) is None


async def test_the_check_constraint_refuses_a_negative_count(
    session: AsyncSession, user: User
) -> None:
    """The documented reset is a hand-written UPDATE; the database, not a comment, is what stops a
    typo in it from handing out an unbounded allowance."""
    with pytest.raises(IntegrityError):
        await session.execute(
            text("UPDATE users SET trial_runs_used = -1 WHERE id = :uid"), {"uid": str(user.id)}
        )
        await session.commit()
    await session.rollback()


async def test_two_concurrent_claims_never_both_take_the_last_run(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    """★ The race, at the last available run. Exactly one caller may win.

    Two sessions, one run left, both claim, both commit. A read-then-write implementation (SELECT
    the count, compare it in Python, UPDATE) hands both callers a success and leaves the stored
    value at `limit + 1` -- one extra run on the maintainer's key per concurrent pair, which is
    what the functional spec proposed accepting. The single conditional UPDATE makes the bound zero
    instead: Postgres takes the row lock, and the loser re-evaluates its WHERE under READ COMMITTED
    against the winner's committed value and finds it false.

    This is the evidence for architecture §4 -- that no advisory lock is needed here.
    """
    async with session_factory() as setup:
        await _set_used(setup, user.id, LIMIT - 1)

    async def claim(session: AsyncSession) -> int | None:
        got = await claim_trial_run(session, user.id, LIMIT)
        await session.commit()
        return got

    async with session_factory() as a, session_factory() as b:
        first, second = await asyncio.gather(claim(a), claim(b))

    assert sorted([first, second], key=lambda v: v is None) == [LIMIT, None], (
        f"exactly one claimer may win the last run, got {first!r} and {second!r}"
    )
    async with session_factory() as check:
        assert await trial_runs_used(check, user.id) == LIMIT


async def test_one_users_exhausted_allowance_does_not_touch_another(
    session: AsyncSession, user: User
) -> None:
    """★ Tenancy at the SQL level. The premise being tested is that the counter is per row -- which
    is obvious right up until someone writes the UPDATE without its `WHERE id`."""
    other = await get_or_create_user(session, "other@example.com")
    await session.commit()

    for _ in range(LIMIT):
        assert await claim_trial_run(session, user.id, LIMIT) is not None
    assert await claim_trial_run(session, user.id, LIMIT) is None
    await session.commit()

    assert await trial_runs_used(session, other.id) == 0
    assert await claim_trial_run(session, other.id, LIMIT) == 1
    await session.commit()
    assert await trial_runs_used(session, user.id) == LIMIT
    assert await trial_runs_used(session, other.id) == 1
