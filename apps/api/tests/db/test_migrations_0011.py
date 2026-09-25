from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from rhapto.db.session import make_engine

# Mirrors `tests/conftest.py`'s `_dsn`/`DEFAULT_TEST_URL`/`API_DIR` rather than importing them:
# `pyproject.toml`'s `pythonpath = ["tests", "tests/unit"]` makes `conftest` an ambiguous bare
# module name once both `tests/db` and `tests/unit` are collected in the same session (each
# directory has its own `conftest.py`), so whichever one Python's import machinery resolves first
# wins the `sys.modules["conftest"]` cache slot -- confirmed by running `pytest tests/unit
# tests/db -q`, which fails this import with `tests/unit/conftest.py`'s module instead.
DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
# This file is at tests/db/, one level deeper than tests/conftest.py, so it needs parents[2]
# (tests/db -> tests -> apps/api) where conftest.py's own API_DIR uses parents[1].
API_DIR = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def test_0011_adds_user_lifecycle_columns(engine: AsyncEngine) -> None:
    def inspect_users(sync_conn):
        cols = {c["name"] for c in inspect(sync_conn).get_columns("users")}
        uniques = {
            tuple(sorted(u["column_names"]))
            for u in inspect(sync_conn).get_unique_constraints("users")
        }
        return cols, uniques

    async with engine.connect() as conn:
        cols, uniques = await conn.run_sync(inspect_users)
    assert {"idp_subject", "last_seen_at", "exempt_from_pruning", "seeded_at"} <= cols
    assert ("idp_subject",) in uniques


async def test_0011_backfills_seeded_at_for_pre_existing_rows() -> None:
    """This is the specific assertion that stops Task 5's bootstrap endpoint from running a
    backfill over the owner's live account: migration 0011 must not just add `seeded_at`, it must
    stamp every row that existed before it ran, so `seeded_at IS NULL` never means "the owner,
    pre-migration" -- only "a genuinely new account". The shared `migrated_db` fixture upgrades
    straight to head and can't exercise "insert a row, then run 0011", so this test drives Alembic
    against its own scratch database: create it, upgrade to 0010, insert a row directly, upgrade to
    0011, assert its seeded_at is no longer NULL, then drop the scratch database. Verified against
    the actual migration file, not assumed: `0011_user_lifecycle_columns.py`'s `upgrade()` ends with
    exactly `UPDATE users SET seeded_at = now() WHERE seeded_at IS NULL` (Step 3, this task).
    """
    import asyncpg
    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0011_backfill_{uuid.uuid4().hex[:8]}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()

    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        os.environ["DATABASE_URL"] = scratch_url
        # alembic/env.py's async runner ends in `asyncio.run(...)`, which cannot be called from
        # inside the event loop this (async) test is already running on -- run it in a thread,
        # the same pattern used throughout this codebase for blocking calls from async code
        # (e.g. `rhapto/api/routers/packages.py`'s `asyncio.to_thread(render_docx, ...)`).
        await asyncio.to_thread(command.upgrade, cfg, "0010")

        scratch_engine = make_engine(scratch_url)
        pre_existing_id = uuid.uuid4()
        try:
            async with scratch_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, settings_json, created_at, updated_at) "
                        "VALUES (:id, :email, '{}'::jsonb, now(), now())"
                    ),
                    {"id": str(pre_existing_id), "email": "owner-pre-0011@example.com"},
                )
            await asyncio.to_thread(command.upgrade, cfg, "0011")
            async with scratch_engine.connect() as conn:
                row = (
                    await conn.execute(
                        text("SELECT seeded_at FROM users WHERE id = :id"),
                        {"id": str(pre_existing_id)},
                    )
                ).first()
            assert row is not None
            assert row[0] is not None
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
