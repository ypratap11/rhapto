"""Migration 0012: `users.trial_runs_used`.

The second test drives Alembic against its own scratch database (the pattern
`test_migrations_0011.py` established) because the shared `migrated_db` fixture upgrades straight to
head and so cannot exercise "a row existed before the column did" -- which is the case that matters:
production has two accounts, and the spec forbids retroactively charging either of them.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from rhapto.db.models import User
from rhapto.db.session import make_engine

# Mirrors `tests/conftest.py`'s `_dsn`/`DEFAULT_TEST_URL`/`API_DIR` rather than importing them, for
# the same reason `test_migrations_0011.py` does: `pythonpath = ["tests", "tests/unit"]` makes a
# bare `conftest` import ambiguous once both `tests/db` and `tests/unit` are collected together.
DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def test_0012_adds_trial_runs_used_not_null_defaulting_to_zero(engine: AsyncEngine) -> None:
    def inspect_users(sync_conn):  # type: ignore[no-untyped-def]
        columns = {c["name"]: c for c in inspect(sync_conn).get_columns("users")}
        checks = {c["name"] for c in inspect(sync_conn).get_check_constraints("users")}
        return columns, checks

    async with engine.connect() as conn:
        columns, checks = await conn.run_sync(inspect_users)

    assert "trial_runs_used" in columns
    column = columns["trial_runs_used"]
    assert column["nullable"] is False
    assert "0" in str(column["default"])
    assert "ck_users_trial_runs_used" in checks


async def test_0012_refuses_a_negative_count(session: AsyncSession, user: User) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(
            text("UPDATE users SET trial_runs_used = -1 WHERE id = :uid"), {"uid": str(user.id)}
        )
        await session.commit()
    await session.rollback()


async def test_0012_does_not_backfill_a_pre_existing_account() -> None:
    """A row that existed before the migration reads 0 afterwards, so both live accounts start with
    a full allowance.

    This is the spec's "no retroactive charging or accounting of the 34 runs already made", asserted
    rather than assumed: `server_default "0"` fills existing rows, and `upgrade()` deliberately has
    no `UPDATE` after it -- unlike 0011, which *does* backfill `seeded_at` and had to.
    """
    import asyncpg
    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0012_{uuid.uuid4().hex[:8]}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()

    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        os.environ["DATABASE_URL"] = scratch_url
        # alembic/env.py ends in `asyncio.run(...)`, which cannot run inside this test's loop.
        await asyncio.to_thread(command.upgrade, cfg, "0011")

        scratch_engine = make_engine(scratch_url)
        pre_existing_id = uuid.uuid4()
        try:
            async with scratch_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, settings_json, created_at, updated_at) "
                        "VALUES (:id, :email, '{}'::jsonb, now(), now())"
                    ),
                    {"id": str(pre_existing_id), "email": "owner-pre-0012@example.com"},
                )
            await asyncio.to_thread(command.upgrade, cfg, "0012")
            async with scratch_engine.connect() as conn:
                row = (
                    await conn.execute(
                        text("SELECT trial_runs_used FROM users WHERE id = :id"),
                        {"id": str(pre_existing_id)},
                    )
                ).first()
            assert row is not None
            assert row[0] == 0, "a pre-existing account must start with its allowance untouched"

            # And the downgrade really is a downgrade: the column goes away cleanly.
            await asyncio.to_thread(command.downgrade, cfg, "0011")
            async with scratch_engine.connect() as conn:

                def columns(sync_conn):  # type: ignore[no-untyped-def]
                    return {c["name"] for c in inspect(sync_conn).get_columns("users")}

                assert "trial_runs_used" not in await conn.run_sync(columns)
        finally:
            await scratch_engine.dispose()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()
        os.environ["DATABASE_URL"] = _dsn(base_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
