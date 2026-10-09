"""Migration 0014: `users.free_import_used_at` and the `coach_events` table.

Same shape as `test_migrations_0013.py`: shared-DB tests at head, plus one test on its own scratch
database for the upgrade -> downgrade -> upgrade round trip. `test_migration_agrees_with_model` is the
drift check (the migration is hand-written, the model is what the API uses).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from rhapto.db.models import COACH_STEPS, CoachEvent, Track, User
from rhapto.db.session import make_engine

DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _inspect(sync_conn):  # type: ignore[no-untyped-def]
    insp = inspect(sync_conn)
    return {
        "columns": {c["name"]: c for c in insp.get_columns("coach_events")},
        "checks": {c["name"]: c["sqltext"] for c in insp.get_check_constraints("coach_events")},
        "uniques": {
            u["name"]: u["column_names"] for u in insp.get_unique_constraints("coach_events")
        },
        # The Postgres dialect reports a UNIQUE constraint's backing index here too (marked
        # `duplicates_constraint`); it is asserted under "uniques", not as a model index (plan review I1).
        "indexes": {
            i["name"]: i
            for i in insp.get_indexes("coach_events")
            if not i.get("duplicates_constraint")
        },
        "fks": insp.get_foreign_keys("coach_events"),
        "user_columns": {c["name"]: c for c in insp.get_columns("users")},
        "track_columns": {c["name"]: c for c in insp.get_columns("tracks")},
    }


async def test_0014_creates_the_table_with_fk_cascade_unique_and_check(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect)
    assert set(found["columns"]) == {"id", "user_id", "step", "day", "created_at"}
    (fk,) = found["fks"]
    assert fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
    assert fk["options"].get("ondelete") == "CASCADE"
    assert "ix_coach_events_user_id" in found["indexes"]
    assert found["uniques"]["uq_coach_events_user_step_day"] == ["user_id", "step", "day"]
    assert set(found["checks"]) == {"ck_coach_events_step"}
    assert found["user_columns"]["free_import_used_at"]["nullable"] is True
    assert found["track_columns"]["score_requested_at"]["nullable"] is False
    assert found["track_columns"]["scored_at"]["nullable"] is True


async def test_migration_agrees_with_model(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.run_sync(_inspect)
    table = CoachEvent.__table__
    assert {c.name for c in table.columns} == set(found["columns"])
    for column in table.columns:
        assert found["columns"][column.name]["nullable"] == column.nullable, column.name
    assert {c.name for c in table.constraints if isinstance(c, CheckConstraint)} == set(
        found["checks"]
    )
    assert {c.name for c in table.constraints if isinstance(c, UniqueConstraint)} == set(
        found["uniques"]
    )
    assert {i.name for i in table.indexes} == set(found["indexes"])
    assert User.__table__.c.free_import_used_at.nullable is True
    assert Track.__table__.c.score_requested_at.nullable is False
    assert Track.__table__.c.scored_at.nullable is True


_INSERT = "INSERT INTO coach_events (id, user_id, step) VALUES (:id, :uid, :step)"


async def _insert(session: AsyncSession, user: User, step: str) -> None:
    await session.execute(
        text(_INSERT), {"id": str(uuid.uuid4()), "uid": str(user.id), "step": step}
    )
    await session.commit()


@pytest.mark.parametrize("step", COACH_STEPS)
async def test_the_live_check_accepts_every_step(
    session: AsyncSession, user: User, step: str
) -> None:
    """Exercises the migrated DB's CHECK against the model's tuple, so a step added to `COACH_STEPS`
    but not to 0014 fails here (names alone would agree)."""
    await _insert(session, user, step)


async def test_a_bad_step_is_rejected_by_the_check(session: AsyncSession, user: User) -> None:
    with pytest.raises(IntegrityError) as info:
        await _insert(session, user, "bogus")
    await session.rollback()
    assert "ck_coach_events_step" in str(info.value.orig)


async def test_the_same_step_twice_in_a_day_is_rejected_by_the_unique(
    session: AsyncSession, user: User
) -> None:
    await _insert(session, user, "started")
    with pytest.raises(IntegrityError) as info:
        await _insert(session, user, "started")
    await session.rollback()
    assert "uq_coach_events_user_step_day" in str(info.value.orig)


async def test_day_defaults_to_the_utc_date(session: AsyncSession, user: User) -> None:
    await _insert(session, user, "resume_in")
    row = (
        await session.execute(
            text(
                "SELECT day, (now() AT TIME ZONE 'UTC')::date AS today FROM coach_events "
                "WHERE user_id = :uid AND step = 'resume_in'"
            ),
            {"uid": str(user.id)},
        )
    ).one()
    assert isinstance(row.day, date) and row.day == row.today


async def test_deleting_the_user_deletes_their_events(session: AsyncSession, user: User) -> None:
    await _insert(session, user, "jobs_shown")
    await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": str(user.id)})
    await session.commit()
    count = (
        await session.execute(
            text("SELECT count(*) FROM coach_events WHERE user_id = :uid"), {"uid": str(user.id)}
        )
    ).scalar_one()
    assert count == 0


async def test_0014_marks_existing_tracks_as_already_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A track that existed before 0014 has scores from the last rescore. Without a backfill it would
    read as "never scored" and a returning tester's coach would wait forever; with it, `scored_at`
    equals `score_requested_at` (both are the migration transaction's now()), so it is ready."""
    import asyncpg
    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0014b_{uuid.uuid4().hex[:8]}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()
    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        monkeypatch.setenv("DATABASE_URL", scratch_url)
        await asyncio.to_thread(command.upgrade, cfg, "0013")
        scratch_engine = make_engine(scratch_url)
        try:
            uid = uuid.uuid4()
            async with scratch_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, settings_json, created_at, updated_at) "
                        "VALUES (:id, 'owner-pre-0014@example.com', '{}'::jsonb, now(), now())"
                    ),
                    {"id": str(uid)},
                )
                await conn.execute(
                    text(
                        "INSERT INTO tracks (id, user_id, position, track_id, name, keywords, resume_base, min_fit, created_at, updated_at) "
                        "VALUES (:id, :uid, 0, 'data-pm', 'Data', ARRAY['etl']::varchar[], 'b', 60, now(), now())"
                    ),
                    {"id": str(uuid.uuid4()), "uid": str(uid)},
                )
            await asyncio.to_thread(command.upgrade, cfg, "0014")
            async with scratch_engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT scored_at IS NOT NULL AND scored_at >= score_requested_at FROM tracks WHERE user_id = :u"
                        ),
                        {"u": str(uid)},
                    )
                ).scalar_one()
            assert row is True
        finally:
            await scratch_engine.dispose()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()


async def test_0014_round_trips_on_a_scratch_database(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncpg
    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0014_{uuid.uuid4().hex[:8]}"
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

        async def state() -> tuple[set[str], set[str]]:
            async with scratch_engine.connect() as conn:

                def read(c):  # type: ignore[no-untyped-def]
                    insp = inspect(c)
                    users = {x["name"] for x in insp.get_columns("users")}
                    tracks = {x["name"] for x in insp.get_columns("tracks")}
                    # one set per side: the free-import flag and both track columns travel together
                    return set(insp.get_table_names()), users | {f"tracks.{n}" for n in tracks}

                return await conn.run_sync(read)

        try:
            await asyncio.to_thread(command.upgrade, cfg, "0013")
            tables, user_cols = await state()
            assert "coach_events" not in tables and "free_import_used_at" not in user_cols
            assert (
                "tracks.scored_at" not in user_cols and "tracks.score_requested_at" not in user_cols
            )
            await asyncio.to_thread(command.upgrade, cfg, "0014")
            tables, user_cols = await state()
            assert "coach_events" in tables and "free_import_used_at" in user_cols
            assert {"tracks.scored_at", "tracks.score_requested_at"} <= user_cols
            await asyncio.to_thread(command.downgrade, cfg, "0013")
            tables, user_cols = await state()
            assert "coach_events" not in tables and "free_import_used_at" not in user_cols
            assert (
                "tracks.scored_at" not in user_cols and "tracks.score_requested_at" not in user_cols
            )
            await asyncio.to_thread(command.upgrade, cfg, "0014")
            tables, user_cols = await state()
            assert "coach_events" in tables and "free_import_used_at" in user_cols
        finally:
            await scratch_engine.dispose()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()
