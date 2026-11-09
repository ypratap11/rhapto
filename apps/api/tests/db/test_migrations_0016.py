"""Migration 0016: `users.blocked_at` and the `admin_actions` audit table.

Same shape as `test_migrations_0014.py`: shared-DB tests at head, scratch databases for the round trip
and the lock-timeout behaviour. `test_migration_agrees_with_model` is the drift check.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from rhapto.db.models import ADMIN_ACTIONS, AdminAction, User
from rhapto.db.session import make_engine

DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[2]
MIGRATION = API_DIR / "alembic" / "versions" / "0016_admin.py"


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _inspect(sync_conn):  # type: ignore[no-untyped-def]
    insp = inspect(sync_conn)
    return {
        "columns": {c["name"]: c for c in insp.get_columns("admin_actions")},
        "checks": {c["name"]: c["sqltext"] for c in insp.get_check_constraints("admin_actions")},
        "indexes": {i["name"]: i for i in insp.get_indexes("admin_actions")},
        "fks": insp.get_foreign_keys("admin_actions"),
        "user_columns": {c["name"]: c for c in insp.get_columns("users")},
    }


async def test_users_blocked_at_is_nullable_timestamptz_no_default(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect)
    col = found["user_columns"]["blocked_at"]
    assert col["nullable"] is True
    assert col["default"] is None
    assert getattr(col["type"], "timezone", False) is True


async def test_admin_actions_columns_check_and_index(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect)
    cols = found["columns"]
    assert set(cols) == {
        "id",
        "created_at",
        "actor_email",
        "action",
        "target_user_id",
        "before_json",
        "after_json",
    }
    assert getattr(cols["actor_email"]["type"], "length", None) == 320
    assert getattr(cols["action"]["type"], "length", None) == 20
    assert cols["created_at"]["nullable"] is False and cols["created_at"]["default"] is not None
    assert cols["target_user_id"]["nullable"] is False
    assert set(found["checks"]) == {"ck_admin_actions_action"}
    index = found["indexes"]["ix_admin_actions_target_created"]
    assert index["column_names"] == ["target_user_id", "created_at"]


async def test_admin_actions_has_no_foreign_key(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        fks = await conn.run_sync(lambda c: inspect(c).get_foreign_keys("admin_actions"))
    assert fks == []


_INSERT = (
    "INSERT INTO admin_actions (id, actor_email, action, target_user_id, before_json, after_json) "
    "VALUES (:id, 'owner@example.com', :action, :target, '{}'::jsonb, '{}'::jsonb)"
)


async def _insert(session: AsyncSession, action: str) -> None:
    await session.execute(
        text(_INSERT), {"id": str(uuid.uuid4()), "action": action, "target": str(uuid.uuid4())}
    )
    await session.commit()


async def test_insert_with_unknown_action_violates_check(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError) as info:
        await _insert(session, "delete")
    await session.rollback()
    assert "ck_admin_actions_action" in str(info.value.orig)


@pytest.mark.parametrize("action", ADMIN_ACTIONS)
async def test_the_live_check_accepts_every_action(session: AsyncSession, action: str) -> None:
    await _insert(session, action)


async def test_migration_agrees_with_model(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect)
    table = AdminAction.__table__
    assert {c.name for c in table.columns} == set(found["columns"])
    for column in table.columns:
        assert found["columns"][column.name]["nullable"] == column.nullable, column.name
    assert {c.name for c in table.constraints if isinstance(c, CheckConstraint)} == set(
        found["checks"]
    )
    assert {i.name for i in table.indexes} == set(found["indexes"])
    assert not table.foreign_keys
    assert User.__table__.c.blocked_at.nullable is True
    assert found["user_columns"]["blocked_at"]["nullable"] is True


def test_upgrade_sets_lock_timeout() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "SET LOCAL lock_timeout = '10s'" in source
    assert source.index("SET LOCAL lock_timeout = '10s'") < source.index("op.add_column")
    assert re.search(r'revision: str = "0016"', source)


@asynccontextmanager
async def _scratch_db(monkeypatch: pytest.MonkeyPatch, tag: str) -> AsyncIterator[str]:
    import asyncpg

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0016{tag}_{uuid.uuid4().hex[:8]}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()
    try:
        monkeypatch.setenv("DATABASE_URL", scratch_url)
        yield scratch_url
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()


async def test_round_trip_upgrade_downgrade_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic.config import Config

    from alembic import command

    async with _scratch_db(monkeypatch, "rt") as scratch_url:
        cfg = Config(str(API_DIR / "alembic.ini"))
        scratch_engine = make_engine(scratch_url)

        async def state() -> tuple[set[str], set[str]]:
            async with scratch_engine.connect() as conn:

                def read(c):  # type: ignore[no-untyped-def]
                    insp = inspect(c)
                    return set(insp.get_table_names()), {
                        x["name"] for x in insp.get_columns("users")
                    }

                return await conn.run_sync(read)

        try:
            await asyncio.to_thread(command.upgrade, cfg, "0015")
            tables, user_cols = await state()
            assert "admin_actions" not in tables and "blocked_at" not in user_cols
            await asyncio.to_thread(command.upgrade, cfg, "0016")
            tables, user_cols = await state()
            assert "admin_actions" in tables and "blocked_at" in user_cols
            await asyncio.to_thread(command.downgrade, cfg, "0015")
            tables, user_cols = await state()
            assert "admin_actions" not in tables and "blocked_at" not in user_cols
            await asyncio.to_thread(command.upgrade, cfg, "0016")
            tables, user_cols = await state()
            assert "admin_actions" in tables and "blocked_at" in user_cols
        finally:
            await scratch_engine.dispose()


async def test_upgrade_fails_fast_when_users_is_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A long reader on `users` must make the migration give up in about 10 s, not queue behind it
    (and, while queued, block every other request on `users`)."""
    import asyncpg
    from alembic.config import Config

    from alembic import command

    async with _scratch_db(monkeypatch, "lk") as scratch_url:
        cfg = Config(str(API_DIR / "alembic.ini"))
        await asyncio.to_thread(command.upgrade, cfg, "0015")
        holder = await asyncpg.connect(_dsn(scratch_url))
        tx = holder.transaction()
        await tx.start()
        scratch_engine = make_engine(scratch_url)
        try:
            await holder.execute("LOCK TABLE users IN ACCESS SHARE MODE")
            started = time.monotonic()
            with pytest.raises(Exception, match="lock timeout"):
                await asyncio.wait_for(asyncio.to_thread(command.upgrade, cfg, "0016"), 40)
            elapsed = time.monotonic() - started
            assert 8 <= elapsed <= 25, elapsed
            async with scratch_engine.connect() as conn:
                cols = await conn.run_sync(
                    lambda c: {x["name"] for x in inspect(c).get_columns("users")}
                )
            assert "blocked_at" not in cols
        finally:
            await tx.rollback()
            await holder.close()
            await scratch_engine.dispose()
