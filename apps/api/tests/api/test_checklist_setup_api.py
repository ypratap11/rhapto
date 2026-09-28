"""The five setup rows, each driven by the condition it claims to check.

Architecture §2 and §8 row 7. Every test here creates the real state -- an all-inactive search set, a
job that is hidden, a block whose period is a blank string -- rather than asserting a value the
endpoint was handed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Aggregator, ResumeBlock
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.discovery.sources.status import keyless_source_names


async def _checklist(client: httpx.AsyncClient) -> dict[str, object]:
    return dict((await client.get("/api/v1/dashboard")).json()["checklist"])


async def _job(
    session: AsyncSession, user_id: uuid.UUID, key: str, **extra: object
) -> jobs_repo.Job:
    job = await jobs_repo.create_discovered_job(
        session,
        user_id,
        source="themuse",
        external_id=key,
        company="ExampleCo",
        title=key,
        location=None,
        url=f"https://example.com/{key}",
        jd_text="x" * 80,
        posted_at=datetime.now(UTC),
        identity_hash=f"h-{key}",
        repost_of=None,
    )
    for attr, value in extra.items():
        setattr(job, attr, value)
    return job


# --- job_sources -----------------------------------------------------------------------------


async def test_a_new_account_is_seeded_with_the_keyless_sources(client: httpx.AsyncClient) -> None:
    """Condition C4, now FIXED rather than merely reported (the owner chose seeding).

    An account used to start with no `aggregators` rows, so `poller.build_specs` polled no aggregator
    while Settings displayed four keyless sources as on. `ensure_account` seeds them, so the row the
    poller reads and the row the page shows are the same row from the first request.
    """
    checklist = await _checklist(client)
    assert checklist["job_sources"] is True
    assert checklist["usable_sources"] == len(keyless_source_names())


async def test_turning_every_keyless_source_off_makes_the_row_not_done(
    client: httpx.AsyncClient,
) -> None:
    """The seed is a starting point, not a floor: a user who switches everything off has no usable
    source, and the checklist must say so rather than report the seed."""
    for source in keyless_source_names():
        assert (
            await client.put(f"/api/v1/settings/sources/{source}", json={"enabled": False})
        ).status_code == 200

    off = await _checklist(client)
    assert off["job_sources"] is False and off["usable_sources"] == 0

    first = keyless_source_names()[0]
    await client.put(f"/api/v1/settings/sources/{first}", json={"enabled": True})
    back = await _checklist(client)
    assert back["job_sources"] is True and back["usable_sources"] == 1


async def test_a_keyed_source_with_no_credentials_is_not_a_usable_source(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """A row saying "enabled" describing something that cannot run. The poller would write
    NO_API_KEY_MESSAGE and nothing could ever arrive, so counting it would be the `resume_template`
    defect in a new place.

    Counted as a delta against the seeded baseline, so the assertion is about the keyed source rather
    than about how many keyless ones the registry happens to ship.
    """
    baseline = int((await _checklist(client))["usable_sources"])  # type: ignore[call-overload]
    async with session_factory() as session:
        session.add(Aggregator(user_id=user_id, source="adzuna", enabled=True, keywords=[]))
        await session.commit()

    assert (await _checklist(client))["usable_sources"] == baseline, (
        "an enabled keyed source with no credentials cannot run, so it must not count"
    )

    await client.put(
        "/api/v1/settings/sources/adzuna",
        json={"enabled": True, "credentials": {"app_id": "a", "app_key": "b"}},
    )
    assert (await _checklist(client))["usable_sources"] == baseline + 1


async def test_the_checklist_and_the_settings_page_agree_about_what_is_ready(
    client: httpx.AsyncClient,
) -> None:
    """Both call the same `usable_source_ids`, and this is what would catch them drifting apart."""
    await client.put("/api/v1/settings/sources/themuse", json={"enabled": True})
    await client.put("/api/v1/settings/sources/remotive", json={"enabled": True})
    rows = (await client.get("/api/v1/settings/sources")).json()
    configured = [r["id"] for r in rows if r["configured"]]
    assert (await _checklist(client))["usable_sources"] == len(configured)


# --- saved_searches --------------------------------------------------------------------------


async def test_an_all_inactive_search_set_is_not_done(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: searches exist and `build_specs` runs none of them, because it filters on
    `active`. A bare `count(searches) > 0` would read done over a poller that fetches nothing."""
    async with session_factory() as session:
        for i in range(3):
            await searches_repo.create_search(
                session,
                user_id,
                name=f"paused {i}",
                keywords=["pm"],
                location=None,
                remote="include",
                active=False,
            )
        await session.commit()

    checklist = await _checklist(client)
    assert checklist["saved_searches"] is False
    assert checklist["active_searches"] == 0


async def test_one_active_search_among_inactive_ones_is_done(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await searches_repo.create_search(
            session,
            user_id,
            name="off",
            keywords=["pm"],
            location=None,
            remote="include",
            active=False,
        )
        await searches_repo.create_search(
            session,
            user_id,
            name="on",
            keywords=["pm"],
            location=None,
            remote="include",
            active=True,
        )
        await session.commit()

    checklist = await _checklist(client)
    assert checklist["saved_searches"] is True
    assert checklist["active_searches"] == 1


# --- jobs_found ------------------------------------------------------------------------------


async def test_a_corpus_that_is_entirely_hidden_or_retired_is_not_jobs_found(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: jobs exist and the default grid shows none of them. A bare
    `count(jobs) > 0` would report the step done over an empty screen."""
    now = datetime.now(UTC)
    async with session_factory() as session:
        await _job(session, user_id, "hidden", hidden_at=now)
        await _job(session, user_id, "retired", unlisted_at=now)
        await session.commit()

    assert (await _checklist(client))["jobs_found"] is False

    async with session_factory() as session:
        await _job(session, user_id, "live")
        await session.commit()

    assert (await _checklist(client))["jobs_found"] is True


async def test_another_users_jobs_do_not_complete_this_users_row(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "other-checklist@example.com")
        await _job(session, other.id, "theirs")
        await session.commit()

    assert (await _checklist(client))["jobs_found"] is False


# --- dateless_blocks (§8 row 7) ---------------------------------------------------------------


async def test_dateless_blocks_counts_blank_periods_as_well_as_missing_ones(
    client: httpx.AsyncClient,
    imported_profile: None,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Two NULL periods and one whitespace-only period.

    The blank-string row is what proves the `btrim` branch exists. `resume_blocks.period` is nullable
    free text, and while the `Block.period` regex cannot admit "" through `PUT /profile/blocks/{id}`,
    nothing constrains a row written by an older import or by hand -- and a block whose period is
    three spaces is exactly as dateless as one with none.
    """
    async with session_factory() as session:
        blocks = list(
            await session.scalars(
                select(ResumeBlock)
                .where(ResumeBlock.user_id == user_id)
                .order_by(ResumeBlock.position)
            )
        )
        assert len(blocks) >= 3, "the example profile should import at least three blocks"
        # Start from a known state: the example profile already ships a block with no period, and a
        # fixture that depends on how many is a fixture that changes meaning when the example does.
        for block in blocks:
            block.period = "2020-2021"
        blocks[0].period = None
        blocks[1].period = None
        blocks[2].period = "   "
        await session.commit()

    assert (await _checklist(client))["dateless_blocks"] == 3


async def test_a_profile_whose_blocks_all_have_periods_counts_none(
    client: httpx.AsyncClient,
    imported_profile: None,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """The contrasting fixture: the count must follow the data, not be a constant."""
    async with session_factory() as session:
        for block in await session.scalars(
            select(ResumeBlock).where(ResumeBlock.user_id == user_id)
        ):
            block.period = "2020-2021"
        await session.commit()

    assert (await _checklist(client))["dateless_blocks"] == 0


# --- the invariants --------------------------------------------------------------------------


async def test_the_checklist_invariants_hold_over_a_populated_account(
    client: httpx.AsyncClient,
    imported_profile: None,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """Each boolean must be exactly the predicate over its own count. Computing the two
    independently is how they would start disagreeing, which is this branch's whole subject."""
    await client.put("/api/v1/settings/sources/themuse", json={"enabled": True})
    async with session_factory() as session:
        await searches_repo.create_search(
            session, user_id, name="on", keywords=["pm"], location=None, remote="include"
        )
        await _job(session, user_id, "live")
        await session.commit()

    checklist = await _checklist(client)
    assert checklist["job_sources"] == (int(checklist["usable_sources"]) > 0)  # type: ignore[call-overload]
    assert checklist["saved_searches"] == (int(checklist["active_searches"]) > 0)  # type: ignore[call-overload]
    source = checklist["llm_key_source"]
    left = checklist["trial_runs_left"]
    assert checklist["llm_key"] == (
        source != "none" and (source != "trial" or int(left or 0) > 0)  # type: ignore[call-overload]
    )
