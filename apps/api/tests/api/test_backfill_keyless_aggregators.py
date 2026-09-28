"""The one-time backfill: does the dry run write nothing, and does `--commit` write the right rows?

This script is the only thing in the branch intended to touch production data, so the property that
matters most is the one asserted first: a dry run must leave the database byte-identical. It is tested
through the same `run()` the command line calls, against a real database, rather than by inspecting
its SQL.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Aggregator
from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.accounts import ensure_account
from rhapto.services.discovery.sources.status import keyless_source_names

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from backfill_keyless_aggregators import plan_backfill, redact, run  # noqa: E402


async def _sources(session: AsyncSession) -> set[tuple[str, str]]:
    rows = await session.execute(select(Aggregator.user_id, Aggregator.source))
    return {(str(user_id), source) for user_id, source in rows.all()}


async def test_the_dry_run_writes_nothing(
    session_factory: async_sessionmaker[AsyncSession],
    migrated_db: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The property this script lives or dies by. An unseeded account is created, the dry run is asked
    what it would do, and the database must be unchanged afterwards."""
    async with session_factory() as session:
        # `get_or_create_user`, not `ensure_account`: this is deliberately the pre-seeding state an
        # existing account is in, which is the whole reason the backfill exists.
        legacy = await get_or_create_user(session, "legacy@example.com")
        await session.commit()
        before = await _sources(session)

    assert before == set(), "the fixture must start with no aggregator rows, or it proves nothing"

    assert await run(migrated_db, commit=False) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert str(len(keyless_source_names())) in out
    # The email is redacted, because this output lands in a terminal and a scrollback.
    assert "legacy@example.com" not in out
    assert redact("legacy@example.com") in out

    async with session_factory() as session:
        assert await _sources(session) == before, "a dry run must not write"
    assert legacy.id is not None


async def test_commit_inserts_the_missing_rows(
    session_factory: async_sessionmaker[AsyncSession], migrated_db: str
) -> None:
    async with session_factory() as session:
        legacy = await get_or_create_user(session, "legacy2@example.com")
        await session.commit()
        legacy_id = legacy.id

    assert await run(migrated_db, commit=True) == 0

    async with session_factory() as session:
        assert await _sources(session) == {
            (str(legacy_id), source) for source in keyless_source_names()
        }
        rows = await session.scalars(select(Aggregator).where(Aggregator.user_id == legacy_id))
        assert all(row.enabled for row in rows)


async def test_commit_is_idempotent_and_leaves_a_disabled_source_disabled(
    session_factory: async_sessionmaker[AsyncSession], migrated_db: str
) -> None:
    """Re-running it must not undo a choice: a backfill that re-enabled a source someone had switched
    off would be worse than the defect it fixes.

    TWO independent mechanisms guarantee it, which is why this test survived a mutation of one of them:
    `plan_backfill` only ever reports sources an account is MISSING, so an existing disabled row is
    never passed to the insert at all; and `seed_keyless_aggregators` uses `ON CONFLICT DO NOTHING`,
    which is what protects the account-creation path, where the whole keyless list is passed every
    time. `test_seeding_is_idempotent_...` in `test_account_seeding.py` is the test that pins the
    second one.
    """
    first = keyless_source_names()[0]
    async with session_factory() as session:
        user = await ensure_account(session, "already@example.com")
        await session.commit()
        row = await session.scalar(
            select(Aggregator).where(Aggregator.user_id == user.id, Aggregator.source == first)
        )
        assert row is not None
        row.enabled = False
        await session.commit()
        user_id = user.id

    assert await run(migrated_db, commit=True) == 0

    async with session_factory() as session:
        rows = {
            r.source: r
            for r in await session.scalars(select(Aggregator).where(Aggregator.user_id == user_id))
        }
    assert len(rows) == len(keyless_source_names()), "no duplicates"
    assert rows[first].enabled is False, "a source the user turned off must stay off"


async def test_an_already_seeded_instance_reports_nothing_to_do(
    session_factory: async_sessionmaker[AsyncSession],
    migrated_db: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with session_factory() as session:
        await ensure_account(session, "seeded-already@example.com")
        await session.commit()

    assert await run(migrated_db, commit=False) == 0
    assert "nothing to do" in capsys.readouterr().out


async def test_the_plan_names_only_the_sources_each_account_is_missing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two accounts in different states in one instance, so the plan is per account rather than a
    single global answer."""
    keyless = keyless_source_names()
    async with session_factory() as session:
        seeded = await ensure_account(session, "plan-seeded@example.com")
        legacy = await get_or_create_user(session, "plan-legacy@example.com")
        await session.commit()
        # And one account missing exactly one source, which is the partial case.
        partial = await ensure_account(session, "plan-partial@example.com")
        await session.commit()
        row = await session.scalar(
            select(Aggregator).where(
                Aggregator.user_id == partial.id, Aggregator.source == keyless[0]
            )
        )
        assert row is not None
        await session.delete(row)
        await session.commit()

        plans = {p.user_id: p for p in await plan_backfill(session, keyless)}

    assert seeded.id not in plans, "a fully seeded account is not in the plan at all"
    assert plans[legacy.id].missing == keyless
    assert plans[partial.id].missing == (keyless[0],)


def test_redact_keeps_the_domain_and_drops_the_local_part() -> None:
    assert redact("someone@example.com") == "s***@example.com"
    assert redact("a@b.co") == "a***@b.co"
    assert redact("nodomain") == "n***"
