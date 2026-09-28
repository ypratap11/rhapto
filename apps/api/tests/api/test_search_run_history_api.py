"""A saved search that has never returned a job, told apart from one with nothing new.

Architecture §8 row 3. Three fixtures, and fixture (c) is the one that matters: it has a poll run
that found five postings and ZERO `jobs` rows carrying that `search_id`. An implementation that asks
`EXISTS (jobs WHERE search_id = ...)` -- the obvious proxy -- reports `ever_found = false` there and
fails. That proxy lies because `jobs.search_id` is ON DELETE SET NULL, job rows are deletable, and
`backfill_public_jobs` deliberately does not copy the column.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import PollRun
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories.users import get_or_create_user


async def _search(
    session: AsyncSession, user_id: uuid.UUID, *, name: str, location: str | None
) -> uuid.UUID:
    row = await searches_repo.create_search(
        session, user_id, name=name, keywords=["tpm"], location=location, remote="include"
    )
    await session.flush()
    return row.id


def _run(
    user_id: uuid.UUID,
    search_id: uuid.UUID,
    *,
    found: int,
    error: str | None = None,
    minutes_ago: int = 0,
) -> PollRun:
    started = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return PollRun(
        user_id=user_id,
        source="adzuna",
        board=None,
        search_id=search_id,
        started_at=started,
        finished_at=started,
        found=found,
        new=0,
        error=error,
    )


async def _one(client: httpx.AsyncClient, search_id: uuid.UUID) -> dict[str, object]:
    rows = (await client.get("/api/v1/searches")).json()
    match = next(r for r in rows if r["id"] == str(search_id))
    return dict(match)


# --- fixture (a): no poll_runs rows at all ---------------------------------------------------


async def test_a_search_that_has_never_run_reports_zero_runs(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Nowhere", location="Nowhereville")
        await session.commit()

    row = await _one(client, search_id)
    assert row["runs"] == 0
    assert row["ever_found"] is False
    assert row["last_run_at"] is None


# --- fixture (b): three runs, none of which found anything -----------------------------------


async def test_three_polls_that_found_nothing_report_runs_without_ever_found(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: `found = 0, error IS NULL` three times -- a source that answered
    successfully and had nothing to give. This is spec §8's "has never returned a job"."""
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Nowhere", location="Nowhereville")
        for i in range(3):
            session.add(_run(user_id, search_id, found=0, minutes_ago=i * 10))
        await session.commit()

    row = await _one(client, search_id)
    assert row["runs"] == 3
    assert row["ever_found"] is False
    assert row["last_run_at"] is not None


# --- fixture (c): the proxy-catching contrast ------------------------------------------------


async def test_a_poll_that_found_five_counts_as_ever_found_with_no_job_rows_at_all(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """One run with `found = 5` and NOT ONE `jobs` row carrying that `search_id`.

    This is the fixture that fails if the implementation asks `jobs.search_id` instead of
    `poll_runs`. The state is ordinary in production: a deleted search detaches its jobs
    (ON DELETE SET NULL), the user can delete jobs, and a bootstrapped account's backfilled rows
    never carried a `search_id` in the first place.
    """
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Found once", location="Remote")
        session.add(_run(user_id, search_id, found=5))
        await session.commit()

        # The premise of the contrast, asserted rather than assumed.
        rows = await jobs_repo.list_jobs(
            session, jobs_repo.JobFilterParams(user_id=user_id, search_id=search_id)
        )
        assert rows == []

    row = await _one(client, search_id)
    assert row["runs"] == 1
    assert row["ever_found"] is True


async def test_a_failed_run_still_counts_as_a_run_but_not_as_a_find(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """An erroring poll is an attempt. It must not read as "never tried", which would send the user
    to edit a search whose real problem is a source that is down."""
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Erroring", location=None)
        session.add(_run(user_id, search_id, found=0, error="HTTP 500"))
        await session.commit()

    row = await _one(client, search_id)
    assert row["runs"] == 1
    assert row["ever_found"] is False


# --- the same three states reach the dashboard rail and the Jobs-page diagnosis ---------------


async def test_the_dashboard_rail_carries_ever_found_per_search(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Both states in one response, so the assertion cannot pass on a constant."""
    async with session_factory() as session:
        never = await _search(session, user_id, name="Never", location="Nowhereville")
        once = await _search(session, user_id, name="Once", location="Remote")
        session.add(_run(user_id, never, found=0))
        session.add(_run(user_id, once, found=5))
        await session.commit()

    rail = (await client.get("/api/v1/dashboard")).json()["saved_searches"]
    by_id = {r["id"]: r for r in rail}
    assert by_id[str(never)]["ever_found"] is False
    assert by_id[str(once)]["ever_found"] is True
    # Both have a zero badge, which is exactly why `ever_found` has to be on the wire.
    assert by_id[str(never)]["new_count"] == 0 and by_id[str(once)]["new_count"] == 0


async def test_the_empty_reason_endpoint_reports_the_searchs_run_history(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Nowhere", location="Nowhereville")
        for i in range(3):
            session.add(_run(user_id, search_id, found=0, minutes_ago=i * 10))
        await session.commit()

    body = (await client.get(f"/api/v1/jobs/empty-reason?search_id={search_id}")).json()
    assert body["search_runs"] == 3
    assert body["search_ever_found"] is False
    assert body["search_location"] == "Nowhereville"


async def test_empty_reason_reports_ever_found_for_a_search_that_has_matched_before(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The contrasting fixture: same endpoint, same shape, different answer."""
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Found once", location="Remote")
        session.add(_run(user_id, search_id, found=5))
        await session.commit()

    body = (await client.get(f"/api/v1/jobs/empty-reason?search_id={search_id}")).json()
    assert body["search_runs"] == 1
    assert body["search_ever_found"] is True


# --- tenancy ---------------------------------------------------------------------------------


async def test_another_users_poll_runs_do_not_count_toward_this_searchs_history(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """`poll_runs.search_id` is a foreign key with no user in it, so the user filter is the only
    thing keeping one account's run history out of another's explanation."""
    async with session_factory() as session:
        search_id = await _search(session, user_id, name="Mine", location=None)
        other = await get_or_create_user(session, "other-run-history@example.com")
        for i in range(4):
            session.add(_run(other.id, search_id, found=9, minutes_ago=i))
        await session.commit()

    row = await _one(client, search_id)
    assert row["runs"] == 0
    assert row["ever_found"] is False


# --- a search with no runs is absent from the grouped read, not missing from the response -----


async def test_searches_with_and_without_history_all_appear(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        a = await _search(session, user_id, name="A", location=None)
        b = await _search(session, user_id, name="B", location=None)
        session.add(_run(user_id, b, found=0))
        await session.commit()

    rows = (await client.get("/api/v1/searches")).json()
    assert {r["id"] for r in rows} == {str(a), str(b)}
    by_id = {r["id"]: r for r in rows}
    assert by_id[str(a)]["runs"] == 0 and by_id[str(b)]["runs"] == 1
