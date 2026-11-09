"""Owner writes: reset free runs, block, unblock. Each takes the row lock and writes its audit row
in the same transaction (architecture section 6, conditions 7 and 8)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import AdminAction, User
from rhapto.db.repositories import admin
from rhapto.db.repositories.admin import (
    ProtectedAccount,
    ResetWouldRaise,
    UserNotFound,
    reset_runs,
    set_blocked,
)
from rhapto.db.repositories.users import claim_trial_run

OWNER = "owner@example.com"
Factory = async_sessionmaker[AsyncSession]


async def _set(session: AsyncSession, user: User, **cols: object) -> None:
    for k, v in cols.items():
        await session.execute(
            text(f"UPDATE users SET {k} = :v WHERE id = :id"), {"v": v, "id": str(user.id)}
        )
    await session.commit()


async def _actions(factory: Factory) -> list[AdminAction]:
    async with factory() as s:
        return list((await s.scalars(select(AdminAction).order_by(AdminAction.created_at))).all())


async def _used(factory: Factory, user: User | uuid.UUID) -> int:
    uid = user if isinstance(user, uuid.UUID) else user.id
    async with factory() as s:
        return int(await s.scalar(select(User.trial_runs_used).where(User.id == uid)) or 0)


async def test_reset_lowers_and_audits_once(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    await _set(session, user, trial_runs_used=3)
    res = await reset_runs(session, actor_email=OWNER, user_id=user.id, to=1)
    assert (res.changed, res.before, res.after) == (True, 3, 1)
    assert await _used(session_factory, user) == 1
    rows = await _actions(session_factory)
    assert len(rows) == 1
    assert rows[0].action == "reset_runs"
    assert rows[0].actor_email == OWNER
    assert rows[0].target_user_id == user.id
    assert rows[0].before_json == {"trial_runs_used": 3}
    assert rows[0].after_json == {"trial_runs_used": 1}


async def test_reset_to_current_is_a_no_op_without_audit(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    """Review Focus 4: a double click is two identical requests; the second changes nothing."""
    await _set(session, user, trial_runs_used=2)
    first = await reset_runs(session, actor_email=OWNER, user_id=user.id, to=0)
    second = await reset_runs(session, actor_email=OWNER, user_id=user.id, to=0)
    assert first.changed is True
    assert (second.changed, second.before, second.after) == (False, 0, 0)
    assert len(await _actions(session_factory)) == 1


async def test_raising_is_409_and_writes_nothing(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    uid = user.id
    await _set(session, user, trial_runs_used=1)
    with pytest.raises(ResetWouldRaise):
        await reset_runs(session, actor_email=OWNER, user_id=uid, to=2)
    assert await _used(session_factory, uid) == 1
    assert await _actions(session_factory) == []


async def test_reset_to_zero_and_negative_is_rejected(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    await _set(session, user, trial_runs_used=2)
    with pytest.raises(ValueError):
        await reset_runs(session, actor_email=OWNER, user_id=user.id, to=-1)
    assert await _used(session_factory, user) == 2
    res = await reset_runs(session, actor_email=OWNER, user_id=user.id, to=0)
    assert res.after == 0


async def test_unknown_user_raises(session: AsyncSession) -> None:
    with pytest.raises(UserNotFound):
        await reset_runs(session, actor_email=OWNER, user_id=uuid.uuid4(), to=0)
    with pytest.raises(UserNotFound):
        await set_blocked(
            session, actor_email=OWNER, user_id=uuid.uuid4(), blocked=True, protected=False
        )


async def test_audit_failure_leaves_user_unchanged(
    session: AsyncSession,
    session_factory: Factory,
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = user.id
    await _set(session, user, trial_runs_used=3)

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("audit insert failed")

    monkeypatch.setattr(admin, "_audit", boom)
    with pytest.raises(RuntimeError):
        await reset_runs(session, actor_email=OWNER, user_id=uid, to=0)
    assert await _used(session_factory, uid) == 3
    assert await _actions(session_factory) == []

    with pytest.raises(RuntimeError):
        await set_blocked(session, actor_email=OWNER, user_id=uid, blocked=True, protected=False)
    async with session_factory() as s:
        assert await s.scalar(select(User.blocked_at).where(User.id == uid)) is None


async def _wait_for_lock_waiter(factory: Factory) -> None:
    async with factory() as probe:
        for _ in range(200):
            n = await probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                )
            )
            if n:
                return
            await asyncio.sleep(0.02)
    raise AssertionError("no session ever waited on a lock")


async def test_reset_concurrent_with_claim_loses_no_update(
    session_factory: Factory, user: User
) -> None:
    # Interleaving 1: the claim holds the row lock; the reset waits, then re-reads 1 and lowers it.
    async with session_factory() as a, session_factory() as b:
        assert await claim_trial_run(a, user.id, 3) == 1
        task = asyncio.create_task(reset_runs(b, actor_email=OWNER, user_id=user.id, to=0))
        await _wait_for_lock_waiter(session_factory)
        assert not task.done()
        await a.commit()
        res = await task
    assert (res.changed, res.before, res.after) == (True, 1, 0)
    assert await _used(session_factory, user) == 0

    # Interleaving 2: the reset holds the lock; the claim waits, then evaluates the lowered value.
    async with session_factory() as s:
        await s.execute(
            text("UPDATE users SET trial_runs_used = 2 WHERE id = :id"), {"id": str(user.id)}
        )
        await s.commit()
    async with session_factory() as holder, session_factory() as a:
        await holder.execute(
            select(User.trial_runs_used).where(User.id == user.id).with_for_update(key_share=True)
        )
        await holder.execute(
            text("UPDATE users SET trial_runs_used = 0 WHERE id = :id"), {"id": str(user.id)}
        )
        claim = asyncio.create_task(claim_trial_run(a, user.id, 3))
        await _wait_for_lock_waiter(session_factory)
        assert not claim.done()
        await holder.commit()
        assert await claim == 1
        await a.commit()
    assert await _used(session_factory, user) == 1


async def test_block_sets_blocked_at_and_audits(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    res = await set_blocked(
        session, actor_email=OWNER, user_id=user.id, blocked=True, protected=False
    )
    assert res.changed is True
    assert res.blocked_at is not None
    async with session_factory() as s:
        stored = await s.scalar(select(User.blocked_at).where(User.id == user.id))
    assert stored == res.blocked_at
    rows = await _actions(session_factory)
    assert [r.action for r in rows] == ["block"]
    assert rows[0].before_json == {"blocked": False}
    assert rows[0].after_json == {"blocked": True}


async def test_unblock_clears_and_audits(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    await set_blocked(session, actor_email=OWNER, user_id=user.id, blocked=True, protected=False)
    res = await set_blocked(
        session, actor_email=OWNER, user_id=user.id, blocked=False, protected=False
    )
    assert (res.changed, res.blocked_at) == (True, None)
    assert [r.action for r in await _actions(session_factory)] == ["block", "unblock"]
    async with session_factory() as s:
        assert await s.scalar(select(User.blocked_at).where(User.id == user.id)) is None


async def test_block_is_idempotent_no_second_audit_row(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    uid = user.id
    first = await set_blocked(
        session, actor_email=OWNER, user_id=uid, blocked=True, protected=False
    )
    again = await set_blocked(
        session, actor_email=OWNER, user_id=uid, blocked=True, protected=False
    )
    assert again.changed is False and again.blocked_at == first.blocked_at
    off = await set_blocked(session, actor_email=OWNER, user_id=uid, blocked=False, protected=False)
    assert off.changed is True
    noop = await set_blocked(
        session, actor_email=OWNER, user_id=uid, blocked=False, protected=False
    )
    assert noop.changed is False
    assert len(await _actions(session_factory)) == 2


async def test_protected_account_cannot_be_blocked_but_can_be_unblocked(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    with pytest.raises(ProtectedAccount):
        await set_blocked(session, actor_email=OWNER, user_id=user.id, blocked=True, protected=True)
    assert await _actions(session_factory) == []
    await set_blocked(session, actor_email=OWNER, user_id=user.id, blocked=True, protected=False)
    res = await set_blocked(
        session, actor_email=OWNER, user_id=user.id, blocked=False, protected=True
    )
    assert res.changed is True and res.blocked_at is None


async def test_free_import_used_at_untouched_by_reset(
    session: AsyncSession, session_factory: Factory, user: User
) -> None:
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    await _set(session, user, trial_runs_used=2, free_import_used_at=stamp)
    await reset_runs(session, actor_email=OWNER, user_id=user.id, to=0)
    async with session_factory() as s:
        got = await s.scalar(select(User.free_import_used_at).where(User.id == user.id))
    assert got == stamp
