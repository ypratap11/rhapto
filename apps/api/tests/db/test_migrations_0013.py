"""Migration 0013: the `feedback` table.

Same shape as `test_migrations_0012.py`: shared-DB tests at head, plus one test on its own scratch
database for the upgrade -> downgrade -> upgrade round trip. `test_migration_agrees_with_model` is the
drift check the repo otherwise lacks (the migration is hand-written, the model is what the API uses).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from rhapto.db.models import PAGE_AREAS, FeedbackRow, User
from rhapto.db.session import make_engine

# Mirrors tests/conftest.py rather than importing it (see test_migrations_0012.py for why).
DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _inspect_feedback(sync_conn):  # type: ignore[no-untyped-def]
    insp = inspect(sync_conn)
    return {
        "columns": {c["name"]: c for c in insp.get_columns("feedback")},
        "checks": {c["name"]: c["sqltext"] for c in insp.get_check_constraints("feedback")},
        "indexes": {i["name"]: i for i in insp.get_indexes("feedback")},
        "fks": insp.get_foreign_keys("feedback"),
    }


async def test_0013_creates_the_table_with_fk_cascade_and_indexes(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect_feedback)

    assert set(found["columns"]) == {
        "id",
        "user_id",
        "form",
        "page_area",
        "schema_version",
        "answers",
        "app_version",
        "job_id",
        "package_id",
        "created_at",
        "updated_at",
    }
    # Exactly one FK (user_id -> users, cascading). No FK on the context pointers: feedback must
    # outlive a job the tester later deletes.
    (fk,) = found["fks"]
    assert fk["referred_table"] == "users"
    assert fk["constrained_columns"] == ["user_id"]
    assert fk["options"].get("ondelete") == "CASCADE"
    assert set(found["indexes"]) == {"ix_feedback_user_id", "ix_feedback_user_created"}
    assert found["indexes"]["ix_feedback_user_created"]["column_names"] == [
        "user_id",
        "created_at",
    ]
    assert set(found["checks"]) == {
        "ck_feedback_form",
        "ck_feedback_page_area",
        "ck_feedback_area_iff_quick",
    }


async def test_migration_agrees_with_model(engine: AsyncEngine) -> None:
    """Columns, nullability, check names and index names in the migrated DB match FeedbackRow."""
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect_feedback)

    table = FeedbackRow.__table__
    assert {c.name for c in table.columns} == set(found["columns"])
    for column in table.columns:
        assert found["columns"][column.name]["nullable"] == column.nullable, column.name
    model_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
    assert model_checks == set(found["checks"])
    assert {i.name for i in table.indexes} == set(found["indexes"])


_INSERT = (
    "INSERT INTO feedback (id, user_id, form, page_area, schema_version, answers, app_version) "
    "VALUES (:id, :uid, :form, :area, 1, CAST(:answers AS jsonb), '0.1.0')"
)


async def _insert(session: AsyncSession, user: User, form: str, area: str | None) -> None:
    await session.execute(
        text(_INSERT),
        {
            "id": str(uuid.uuid4()),
            "uid": str(user.id),
            "form": form,
            "area": area,
            "answers": json.dumps({}),
        },
    )
    await session.commit()


@pytest.mark.parametrize(
    ("form", "area", "constraint"),
    [
        ("bogus", None, "ck_feedback_form"),
        ("quick", "nowhere", "ck_feedback_page_area"),
        ("quick", None, "ck_feedback_area_iff_quick"),
        ("survey", "dashboard", "ck_feedback_area_iff_quick"),
    ],
)
async def test_each_check_rejects_a_bad_row(
    session: AsyncSession, user: User, form: str, area: str | None, constraint: str
) -> None:
    with pytest.raises(IntegrityError) as info:
        await _insert(session, user, form, area)
    await session.rollback()
    assert constraint in str(info.value.orig)


async def test_good_rows_are_accepted(session: AsyncSession, user: User) -> None:
    await _insert(session, user, "survey", None)


@pytest.mark.parametrize("area", PAGE_AREAS)
async def test_the_live_check_accepts_every_page_area(
    session: AsyncSession, user: User, area: str
) -> None:
    """Exercises the migrated DB's CHECK against the model's tuple, so an area added to `PAGE_AREAS`
    but not to 0013 fails here (names alone would agree)."""
    await _insert(session, user, "quick", area)


async def test_0013_round_trips_on_a_scratch_database(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncpg
    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0013_{uuid.uuid4().hex[:8]}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()

    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        monkeypatch.setenv("DATABASE_URL", scratch_url)
        scratch_engine = make_engine(scratch_url)

        async def tables() -> set[str]:
            async with scratch_engine.connect() as conn:
                return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))

        try:
            # alembic/env.py ends in `asyncio.run(...)`, which cannot run inside this test's loop.
            await asyncio.to_thread(command.upgrade, cfg, "0012")
            assert "feedback" not in await tables()
            await asyncio.to_thread(command.upgrade, cfg, "0013")
            assert "feedback" in await tables()
            await asyncio.to_thread(command.downgrade, cfg, "0012")
            assert "feedback" not in await tables()
            await asyncio.to_thread(command.upgrade, cfg, "0013")
            assert "feedback" in await tables()
        finally:
            await scratch_engine.dispose()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()
