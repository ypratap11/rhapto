"""`GET /jobs/empty-reason`: does the diagnosis name the real cause?

Every fixture here creates the *condition* -- a field the user has no track in, a corpus older
than the requested window, a source nobody polled -- and then asserts the cause the API reports.
None of them asserts a string that lives in the implementation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.models.profile.tracks import Track

REASON = "/api/v1/jobs/empty-reason"


async def _track(session: AsyncSession, user_id: uuid.UUID, track_id: str, field: str) -> None:
    await profile_repo.upsert_track(
        session,
        user_id,
        Track(
            id=track_id,
            name=track_id,
            resume_base="b",
            min_fit=60,
            keywords=[track_id],
            field=field,
        ),
    )


async def _job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    key: str,
    source: str = "themuse",
    track: str | None = None,
    posted_at: datetime | None = None,
    age_days: int = 0,
    search_id: uuid.UUID | None = None,
) -> uuid.UUID:
    job = await jobs_repo.create_discovered_job(
        session,
        user_id,
        source=source,
        external_id=key,
        company="ExampleCo",
        title=f"{key} role",
        location=None,
        url=f"https://example.com/{key}",
        jd_text="x" * 80,
        posted_at=posted_at
        if posted_at is not None
        else datetime.now(UTC) - timedelta(days=age_days),
        identity_hash=f"h-{key}",
        repost_of=None,
        search_id=search_id,
    )
    if track is not None:
        job.best_track_id, job.best_fit = track, 80
    return job.id


async def test_the_route_is_not_shadowed_by_the_job_id_route(client: httpx.AsyncClient) -> None:
    """`/{job_id}` is declared after this one on purpose. If the order ever regresses, FastAPI
    matches the path parameter first and answers 422 because "empty-reason" is not a UUID."""
    response = await client.get(REASON)
    assert response.status_code == 200, response.text


async def test_an_account_with_no_jobs_at_all_says_so(client: httpx.AsyncClient) -> None:
    body = (await client.get(REASON)).json()
    assert body["cause"] == "no_jobs"
    assert body["total"] == 0
    assert body["filter_id"] is None


# --- Row 1: a field the user has no track in ------------------------------------------------


async def test_a_field_with_no_tracks_is_a_filter_that_can_never_match(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: the user's only track is in one field and they ask about another.

    This is not "nothing matched right now" -- it can never match -- and the distinction is the
    whole reason this endpoint exists.
    """
    async with session_factory() as session:
        await _track(session, user_id, "tpm", "program-project-management")
        for i in range(3):
            await _job(session, user_id, key=f"j{i}", track="tpm")
        await session.commit()

    # Sanity: the listing really is empty for this field, so there is something to explain.
    assert (await client.get("/api/v1/jobs?field=engineering")).json() == []

    body = (await client.get(f"{REASON}?field=engineering")).json()
    assert body["cause"] == "field_without_tracks"
    assert body["total"] == 3
    # Display names, resolved from the taxonomy and from the user's own tracks -- not literals.
    assert body["field_name"] == "Engineering"
    assert body["user_field_names"] == ["Program and Project Management"]


async def test_a_field_the_user_does_have_a_track_in_is_not_field_without_tracks(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The mutation of the fixture above, as a test: move the track into the requested field and
    the same call must stop reporting `field_without_tracks`."""
    async with session_factory() as session:
        await _track(session, user_id, "tpm", "engineering")
        await _job(session, user_id, key="j0", track="tpm")
        await session.commit()

    body = (await client.get(f"{REASON}?field=engineering")).json()
    assert body["cause"] != "field_without_tracks"
    # The grid is not empty at all here, which is itself the honest answer.
    assert body["cause"] == "nothing_matched"


async def test_user_field_names_lists_every_field_the_user_has_a_track_in(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await _track(session, user_id, "tpm", "program-project-management")
        await _track(session, user_id, "des", "design")
        await _job(session, user_id, key="j0", track="tpm")
        await session.commit()

    body = (await client.get(f"{REASON}?field=engineering")).json()
    assert body["cause"] == "field_without_tracks"
    assert body["user_field_names"] == ["Design", "Program and Project Management"]


# --- Row 2: one filter excluded everything --------------------------------------------------


async def test_a_date_window_that_excluded_everything_is_blamed_with_a_widen_target(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: ten dateless jobs first seen 200 days ago, asked for within 24h."""
    async with session_factory() as session:
        for i in range(10):
            job_id = await _job(session, user_id, key=f"old{i}")
            job = await jobs_repo.get_job(session, user_id, job_id)
            assert job is not None
            job.posted_at = None
            job.discovered_at = datetime.now(UTC) - timedelta(days=200)
        await session.commit()

    assert (await client.get("/api/v1/jobs?posted_within=24h")).json() == []

    body = (await client.get(f"{REASON}?posted_within=24h")).json()
    assert body["cause"] == "filter"
    assert body["filter_id"] == "posted_within"
    assert body["filter_value"] == "24h"
    assert body["would_match"] == 10
    assert body["total"] == 10


async def test_a_source_filter_that_excluded_everything_blames_sources_not_the_date(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """A second, different fixture for the same cause: the blame must follow the fixture, not a
    constant. Ten fresh jobs from `themuse`, filtered to `adzuna`."""
    async with session_factory() as session:
        for i in range(10):
            await _job(session, user_id, key=f"m{i}", source="themuse")
        await session.commit()

    body = (await client.get(f"{REASON}?sources=adzuna")).json()
    assert body["cause"] == "filter"
    assert body["filter_id"] == "sources"
    assert body["filter_value"] == "adzuna"
    assert body["would_match"] == 10


async def test_the_most_restrictive_filter_is_blamed_not_the_first(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Two filters are each individually fatal, and removing one reveals more than the other.

    Ten jobs on `themuse` that are 200 days old, plus two on `adzuna` that are fresh. Asking for
    `sources=themuse&posted_within=24h` matches nothing. Dropping `posted_within` reveals ten;
    dropping `sources` reveals two. The user wants the date widened, so that is what is blamed --
    and `sources` comes FIRST in registry order, so a first-wins implementation would fail here.
    """
    async with session_factory() as session:
        for i in range(10):
            job_id = await _job(session, user_id, key=f"old{i}", source="themuse")
            job = await jobs_repo.get_job(session, user_id, job_id)
            assert job is not None
            job.discovered_at = datetime.now(UTC) - timedelta(days=200)
            job.posted_at = None
        for i in range(2):
            await _job(session, user_id, key=f"fresh{i}", source="adzuna")
        await session.commit()

    body = (await client.get(f"{REASON}?sources=themuse&posted_within=24h")).json()
    assert body["cause"] == "filter"
    assert body["filter_id"] == "posted_within"
    assert body["would_match"] == 10


async def test_two_filters_that_only_exclude_everything_together_blame_nobody(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """`combination` is the honest answer when no single removal helps.

    Three old `themuse` jobs, asked for as fresh `adzuna` jobs. Dropping `sources` still matches
    nothing (they are all too old); dropping `posted_within` still matches nothing (none is on
    adzuna). No single widen helps, so no filter is blamed -- naming one would be a guess, which is
    the same class of fabrication as inventing a city name.
    """
    async with session_factory() as session:
        for i in range(3):
            job_id = await _job(session, user_id, key=f"old-muse{i}", source="themuse")
            job = await jobs_repo.get_job(session, user_id, job_id)
            assert job is not None
            job.discovered_at = datetime.now(UTC) - timedelta(days=200)
            job.posted_at = None
        await session.commit()

    body = (await client.get(f"{REASON}?sources=adzuna&posted_within=24h")).json()
    assert body["cause"] == "combination"
    assert body["filter_id"] is None
    assert body["would_match"] is None


async def test_a_grid_that_is_not_empty_is_reported_as_such(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await _job(session, user_id, key="j0")
        await session.commit()

    body = (await client.get(REASON)).json()
    assert body["cause"] == "nothing_matched"
    assert body["filter_id"] is None


async def test_every_job_hidden_blames_the_hidden_switch(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """`hidden` is always-active rather than switched on by a value, so it needs its own proof that
    it can be blamed. The real condition: the user said "not interested" to everything."""
    async with session_factory() as session:
        for i in range(4):
            job_id = await _job(session, user_id, key=f"h{i}")
            job = await jobs_repo.get_job(session, user_id, job_id)
            assert job is not None
            jobs_repo.set_hidden(job, True)
        await session.commit()

    body = (await client.get(REASON)).json()
    assert body["cause"] == "filter"
    assert body["filter_id"] == "hidden"
    assert body["would_match"] == 4


# --- Row 3 (partial): the saved search's own identity travels with the diagnosis -------------


async def test_a_saved_search_diagnosis_carries_the_searchs_own_name_and_location(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        search = await searches_repo.create_search(
            session,
            user_id,
            name="Nowhere roles",
            keywords=["tpm"],
            location="Nowhereville",
            remote="include",
        )
        # A job exists, but not from this search -- so the search's own view is empty.
        await _job(session, user_id, key="j0")
        await session.commit()
        search_id = search.id

    body = (await client.get(f"{REASON}?search_id={search_id}")).json()
    assert body["cause"] == "filter"
    assert body["filter_id"] == "search_id"
    assert body["search_name"] == "Nowhere roles"
    assert body["search_location"] == "Nowhereville"


# --- C7: no suggestion field, no asserted cause ----------------------------------------------


async def test_the_response_never_offers_a_suggested_location_or_an_asserted_cause(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Condition C7. Nothing in this codebase can tell an unrecognised location from an empty
    market, and there is no gazetteer to draw an alternative location from -- so no field here may
    hold one. Pinned as an assertion about the response's keys so a later implementer cannot
    quietly add one and fill it with a literal.
    """
    async with session_factory() as session:
        search = await searches_repo.create_search(
            session,
            user_id,
            name="S",
            keywords=["tpm"],
            location="San Francisco Bay Area",
            remote="include",
        )
        await _job(session, user_id, key="j0")
        await session.commit()
        search_id = search.id

    body = (await client.get(f"{REASON}?search_id={search_id}")).json()
    forbidden = {
        "suggestion",
        "suggested_location",
        "location_suggestion",
        "try_location",
        "alternative_location",
        "reason_guess",
        "likely_cause",
        "asserted_cause",
    }
    assert forbidden.isdisjoint(body.keys()), sorted(forbidden & set(body.keys()))
    # And no value in the response is a place name this code invented: every string present must
    # have come from the fixture or be a structural value.
    assert body["search_location"] == "San Francisco Bay Area"


# --- Tenancy ---------------------------------------------------------------------------------


async def test_another_users_matching_jobs_cannot_shape_this_users_diagnosis(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """User B holds jobs matching every filter; user A must still be told their corpus is empty.

    Tenancy is a base predicate applied outside the registry, so no leave-one-out can drop it.
    """
    async with session_factory() as session:
        other = await get_or_create_user(session, "other-empty-reason@example.com")
        for i in range(25):
            await _job(session, other.id, key=f"b{i}")
        await session.commit()

    body = (await client.get(REASON)).json()
    assert body["total"] == 0
    assert body["cause"] == "no_jobs"


@pytest.mark.parametrize("field", ["not-a-field", ""])
async def test_an_unknown_taxonomy_field_is_422_on_both_endpoints(
    client: httpx.AsyncClient, field: str
) -> None:
    """The shared `Depends(job_filters)` is what makes this true of both endpoints at once."""
    assert (await client.get(f"{REASON}?field={field}")).status_code == 422
    assert (await client.get(f"/api/v1/jobs?field={field}")).status_code == 422


# --- C2 as a test, not a grep ------------------------------------------------------------------

#: Filter sets spanning the parameters the Jobs page really sends, plus a couple it does not, chosen
#: to produce empty and non-empty results and several different blamed filters.
FILTER_SETS = [
    "",
    "?posted_within=24h",
    "?posted_within=any",
    "?sources=adzuna",
    "?sources=themuse",
    "?sources=themuse,adzuna",
    "?field=program-project-management",
    "?field=engineering",
    "?hidden=true",
    "?hidden=true&posted_within=24h",
    "?sources=adzuna&posted_within=24h",
    "?sources=themuse&posted_within=any",
    "?field=engineering&sources=themuse",
    "?recommended=true",
    "?track=tpm",
    "?bucket=low",
]


async def test_the_listing_is_empty_exactly_when_the_diagnosis_says_it_is(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Condition C2, enforced by behaviour rather than by a grep in a report.

    Nothing today fails if someone re-adds an inline `query = query.where(...)` to `list_jobs` for a
    predicate that is not in `JOB_FILTERS`: the listing would narrow by it and the diagnosis would
    not know, so an empty grid would come back with `cause = "nothing_matched"` -- the endpoint saying
    "there are rows for these filters" about a grid with none.

    That is precisely what this asserts, over sixteen filter sets: `GET /jobs` returns rows if and
    only if the diagnosis declines to explain an empty result. One statement of the registry's whole
    purpose, and it cannot be satisfied by a duplicated predicate.
    """
    async with session_factory() as session:
        await _track(session, user_id, "tpm", "program-project-management")
        # A spread that makes several of the sets above empty and several non-empty: two fresh, one
        # old and dateless, one hidden, one on a second source.
        fresh = await _job(session, user_id, key="fresh", source="themuse", track="tpm")
        await _job(session, user_id, key="second", source="adzuna", track="tpm")
        old_id = await _job(session, user_id, key="old", source="themuse", track="tpm")
        old = await jobs_repo.get_job(session, user_id, old_id)
        assert old is not None
        old.posted_at, old.discovered_at = None, datetime.now(UTC) - timedelta(days=200)
        hidden_id = await _job(session, user_id, key="hidden", source="themuse", track="tpm")
        hidden = await jobs_repo.get_job(session, user_id, hidden_id)
        assert hidden is not None
        jobs_repo.set_hidden(hidden, True)
        assert fresh is not None
        await session.commit()

    empty_sets: list[str] = []
    for query in FILTER_SETS:
        rows = (await client.get(f"/api/v1/jobs{query}")).json()
        body = (await client.get(f"{REASON}{query}")).json()
        listing_empty = len(rows) == 0
        diagnosis_explains = body["cause"] != "nothing_matched"
        assert listing_empty == diagnosis_explains, (
            f"{query or '(no filters)'}: GET /jobs returned {len(rows)} row(s) while "
            f"empty-reason said cause={body['cause']!r}"
        )
        if listing_empty:
            empty_sets.append(query)

    # The fixture has to exercise both sides, or the biconditional above is vacuously true.
    assert empty_sets, "no filter set produced an empty grid; the fixture proves nothing"
    assert len(empty_sets) < len(FILTER_SETS), "every filter set was empty; same problem"
