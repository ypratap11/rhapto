from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.models.profile.tracks import Track


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> dict[str, Any]:
    """Four jobs across two sources, two tracks, one saved search and three posting ages."""
    async with session_factory() as session:
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(
                id="tpm",
                name="TPM",
                resume_base="b",
                min_fit=60,
                keywords=["tpm"],
                field="program-project-management",
                role="technical-program-manager",
            ),
        )
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(
                id="be",
                name="Backend",
                resume_base="b",
                min_fit=60,
                keywords=["backend"],
                field="engineering",
                role="backend",
            ),
        )
        search = await searches_repo.create_search(
            session, user_id, name="Platform", keywords=["tpm"], location=None, remote="include"
        )
        now = datetime.now(UTC)
        made: dict[str, Any] = {"search_id": str(search.id)}
        for key, source, track, age_days, search_id in [
            ("fresh", "themuse", "tpm", 0, search.id),
            ("week", "remotive", "tpm", 4, None),
            ("old", "themuse", "be", 20, None),
            ("ancient", "greenhouse", "be", 200, None),
        ]:
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
                posted_at=now - timedelta(days=age_days),
                identity_hash=f"h-{key}",
                repost_of=None,
                search_id=search_id,
            )
            job.best_track_id = track
            job.best_fit = 80
            made[key] = str(job.id)
        await session.commit()
        return made


async def test_ids_selects_exactly_those_jobs(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    wanted = f"{made['fresh']},{made['old']}"
    rows = (await client.get(f"/api/v1/jobs?ids={wanted}")).json()
    assert {j["id"] for j in rows} == {made["fresh"], made["old"]}


async def test_too_many_ids_is_422(client: httpx.AsyncClient) -> None:
    ids = ",".join(str(uuid.uuid4()) for _ in range(201))
    assert (await client.get(f"/api/v1/jobs?ids={ids}")).status_code == 422
    assert (await client.get("/api/v1/jobs?ids=not-a-uuid")).status_code == 422


async def test_search_id_filters_to_one_saved_search(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get(f"/api/v1/jobs?search_id={made['search_id']}")).json()
    assert [j["id"] for j in rows] == [made["fresh"]]


async def test_posted_within_windows(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    assert {j["id"] for j in (await client.get("/api/v1/jobs?posted_within=24h")).json()} == {
        made["fresh"]
    }
    assert {j["id"] for j in (await client.get("/api/v1/jobs?posted_within=7d")).json()} == {
        made["fresh"],
        made["week"],
    }
    assert len((await client.get("/api/v1/jobs?posted_within=30d")).json()) == 3
    assert len((await client.get("/api/v1/jobs?posted_within=90d")).json()) == 3
    assert len((await client.get("/api/v1/jobs?posted_within=any")).json()) == 4


async def test_default_posted_within_is_90d(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    # No `posted_within` on the request at all -- the endpoint's own default (90d) must apply,
    # the same as passing `posted_within=90d` explicitly, excluding the 200-day-old job.
    rows = (await client.get("/api/v1/jobs")).json()
    assert {j["id"] for j in rows} == {made["fresh"], made["week"], made["old"]}
    # `posted_within=any` remains the escape hatch back to the older jobs.
    any_rows = (await client.get("/api/v1/jobs?posted_within=any")).json()
    assert {j["id"] for j in any_rows} == {
        made["fresh"],
        made["week"],
        made["old"],
        made["ancient"],
    }


async def test_default_sort_is_newest_first(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    # No `sort` on the request -- the endpoint's own default (newest) must apply and order the
    # (default-90d-windowed) results most-recently-posted first.
    rows = (await client.get("/api/v1/jobs")).json()
    assert [j["id"] for j in rows] == [made["fresh"], made["week"], made["old"]]


async def test_sources_filter(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    # `posted_within=any` keeps this test about the sources filter, not the default 90d window --
    # `ancient` is 200 days old and would otherwise be dropped by the default before sources even
    # gets a say.
    rows = (await client.get("/api/v1/jobs?sources=remotive,greenhouse&posted_within=any")).json()
    assert {j["id"] for j in rows} == {made["week"], made["ancient"]}


async def test_field_maps_to_its_tracks(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs?field=program-project-management")).json()
    assert {j["id"] for j in rows} == {made["fresh"], made["week"]}
    # A field the user has no track in is an empty result, not an error.
    assert (await client.get("/api/v1/jobs?field=design")).json() == []
    assert (await client.get("/api/v1/jobs?field=not-a-field")).status_code == 422


async def test_recommended_excludes_tailored_applied_hidden_and_unlisted(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    tailored_package: dict[str, Any],
) -> None:
    made = await _seed(session_factory, user_id)
    await client.post(f"/api/v1/jobs/{made['week']}/hide")
    await client.post("/api/v1/applications", json={"job_id": made["old"]})
    async with session_factory() as session:
        job = await jobs_repo.get_job(session, user_id, uuid.UUID(made["ancient"]))
        assert job is not None
        job.unlisted_at = datetime.now(UTC)
        await session.commit()
    rows = (await client.get("/api/v1/jobs?recommended=true")).json()
    # `fresh` is the only one left: the tailored job has a package, and the other three are
    # applied, hidden and unlisted.
    assert [j["id"] for j in rows] == [made["fresh"]]


async def test_filters_compose_with_sort(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs?sources=themuse&sort=newest")).json()
    assert [j["id"] for j in rows] == [made["fresh"], made["old"]]
