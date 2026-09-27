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

    Sequenced rather than left to the scheduler, because a test that merely `gather`s two claims and
    hopes they interleave passes against a broken implementation whenever the first one happens to
    finish first -- verified: the read-then-write mutant below survived that version of this test.

    So the interleaving is forced. A claims (its UPDATE takes the row lock and is left uncommitted),
    B claims on its own session and blocks on that lock, A commits, and only then is B allowed to
    finish. The single conditional UPDATE re-evaluates its WHERE under READ COMMITTED against A's
    committed value and finds it false, so B gets None: the bound on concurrent overrun is zero extra
    runs, not one, and no advisory lock is needed (architecture §4).

    A read-then-write implementation fails here for a reason worth stating: its SELECT does not block
    on a row lock -- MVCC hands it the pre-commit value 2 straight away -- so it decides "2 < 3, go
    ahead", blocks only on the UPDATE, and then writes anyway once A commits. B would be told it had
    won the run A already took.
    """
    async with session_factory() as setup:
        await _set_used(setup, user.id, LIMIT - 1)

    async with session_factory() as a, session_factory() as b:
        first = await claim_trial_run(a, user.id, LIMIT)
        assert first == LIMIT, "the first claimer takes the last run"

        second_task = asyncio.create_task(claim_trial_run(b, user.id, LIMIT))
        # Let B reach the database and queue behind A's uncommitted row lock. Polling `pg_locks`
        # would need a third connection; "B has not finished" is the only property the assertions
        # below need, and it is what makes them deterministic.
        for _ in range(100):
            await asyncio.sleep(0.02)
            if second_task.done():
                break
        assert not second_task.done(), (
            "B must still be queued behind A's row lock, not already finished"
        )

        await a.commit()
        second = await second_task
        await b.commit()

    assert second is None, f"only one claimer may win the last run, B also got {second!r}"
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
