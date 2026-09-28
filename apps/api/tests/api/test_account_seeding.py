"""A new account can actually poll something, and the display cannot disagree with the poller.

The defect the owner chose to fix: `poller.build_specs` builds its work list only from `aggregators`
rows that exist and are enabled, so an account with no rows polled no aggregators — while
`GET /settings/sources` displayed four keyless sources as switched on. On the live instance the second
real account was in exactly that state.

Two separate guarantees are tested here, and the second is the one that matters most:

1. `ensure_account` seeds enabled rows for the keyless sources, so a new account works.
2. The display reads the row and nothing else, so even a MISSED seed is honest-but-off rather than a
   lie. Seeding is the convenience; this is the invariant.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Aggregator
from rhapto.db.repositories import profile as profile_repo
from rhapto.services.accounts import ensure_account
from rhapto.services.discovery.poller import build_specs
from rhapto.services.discovery.sources.status import keyless_source_names


async def test_a_new_account_has_an_enabled_row_for_every_keyless_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        user = await ensure_account(session, "seeded@example.com")
        await session.commit()
        rows = {r.source: r for r in await profile_repo.list_aggregators(session, user.id)}

    assert set(rows) == set(keyless_source_names())
    assert all(row.enabled for row in rows.values())
    # Keyed sources are deliberately NOT seeded: enabling one with no credentials would only produce
    # failing polls and a row that says "enabled" about something that cannot run.
    assert "adzuna" not in rows


async def test_the_poller_actually_builds_work_for_a_freshly_seeded_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The assertion that matters, and it is made against the POLLER rather than against the rows.

    A test that only checked the `aggregators` rows would confirm this code's own premise. What the
    defect was about is `build_specs` returning no aggregator work, so this asks `build_specs`.
    """
    async with session_factory() as session:
        user = await ensure_account(session, "poller-seeded@example.com")
        # One track, so `derive_searches` has something to derive a search from.
        from rhapto.models.profile.tracks import Track

        await profile_repo.upsert_track(
            session,
            user.id,
            Track(id="tpm", name="TPM", resume_base="b", min_fit=60, keywords=["program manager"]),
        )
        await session.commit()

        specs = await build_specs(session, user.id)

    aggregator_specs = {s.source for s in specs if s.search is not None}
    assert aggregator_specs == set(keyless_source_names()), (
        "a seeded account must produce aggregator work on its first poll"
    )


async def test_seeding_is_idempotent_and_never_re_enables_a_source_the_user_turned_off(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`ensure_account` runs on every sign-in in access mode, so this is not a hypothetical.

    If it re-enabled rows, a user who switched The Muse off would find it back on at their next visit
    — a setting silently overwritten by a convenience.
    """
    first = keyless_source_names()[0]
    async with session_factory() as session:
        user = await ensure_account(session, "idempotent@example.com")
        await session.commit()
        rows = {r.source: r for r in await profile_repo.list_aggregators(session, user.id)}
        rows[first].enabled = False
        await session.commit()

    async with session_factory() as session:
        again = await ensure_account(session, "idempotent@example.com")
        await session.commit()
        assert again.id == user.id
        after = {r.source: r for r in await profile_repo.list_aggregators(session, again.id)}

    assert len(after) == len(keyless_source_names()), "no duplicate rows"
    assert after[first].enabled is False, "a source the user turned off must stay off"


async def test_the_display_never_reports_a_source_with_no_row_as_enabled(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The invariant that makes a missed seed harmless.

    This is the state of an account created before seeding existed, and of any future
    account-creation path that forgets to call `ensure_account`. The page must agree with the poller —
    which will skip the source — rather than defaulting it to on. Before this branch it defaulted to
    on, which is how a real account spent weeks looking configured and fetching nothing.
    """
    async with session_factory() as session:
        await session.execute(delete(Aggregator).where(Aggregator.user_id == user_id))
        await session.commit()

    rows = (await client.get("/api/v1/settings/sources")).json()
    assert rows, "the registry should ship at least one aggregator source"
    assert all(r["enabled"] is False for r in rows)
    assert all(r["configured"] is False for r in rows)

    # And the two surfaces still agree with each other in that state.
    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["job_sources"] is False and checklist["usable_sources"] == 0


async def test_two_accounts_are_seeded_independently(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """This instance is multi-tenant with real second and third users, so the seed is per user."""
    async with session_factory() as session:
        a = await ensure_account(session, "tenant-a@example.com")
        b = await ensure_account(session, "tenant-b@example.com")
        await session.commit()
        assert a.id != b.id
        for user in (a, b):
            sources = {r.source for r in await profile_repo.list_aggregators(session, user.id)}
            assert sources == set(keyless_source_names())
        # No row belongs to the wrong account.
        owners = set((await session.execute(select(Aggregator.user_id, Aggregator.source))).all())
        assert owners == {(u.id, s) for u in (a, b) for s in keyless_source_names()}
