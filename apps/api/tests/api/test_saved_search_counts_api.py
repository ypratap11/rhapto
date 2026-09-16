from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def test_a_search_can_be_created_from_a_bare_query(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/searches", json={"query": "program manager"})
    assert created.status_code == 201
    body = created.json()
    # The form sends what the user typed; the name and the keyword list follow from it.
    assert body["name"] == "program manager"
    assert body["keywords"] == ["program manager"]
    assert body["new_count"] == 0 and body["last_viewed_at"] is None


async def test_keywords_still_work_and_an_explicit_name_wins(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/searches", json={"name": "Platform", "keywords": ["tpm", "delivery"]}
    )
    assert created.json()["name"] == "Platform"
    assert created.json()["keywords"] == ["tpm", "delivery"]


async def test_query_and_keywords_together_are_rejected(client: httpx.AsyncClient) -> None:
    both = await client.post("/api/v1/searches", json={"query": "pm", "keywords": ["pm"]})
    assert both.status_code == 422
    neither = await client.post("/api/v1/searches", json={"name": "x"})
    assert neither.status_code == 422


async def _job_for(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    search_id: uuid.UUID,
    external_id: str,
    **kwargs: Any,
) -> uuid.UUID:
    async with session_factory() as session:
        job = await jobs_repo.create_discovered_job(
            session,
            user_id,
            source="themuse",
            external_id=external_id,
            company="ExampleCo",
            title="Program Manager",
            location=None,
            url=f"https://example.com/{external_id}",
            jd_text="x" * 80,
            posted_at=None,
            identity_hash=f"h-{external_id}",
            repost_of=None,
            search_id=search_id,
        )
        for key, value in kwargs.items():
            setattr(job, key, value)
        await session.commit()
        return job.id


async def test_new_count_counts_jobs_discovered_since_the_last_view(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    search_id = uuid.UUID(
        (await client.post("/api/v1/searches", json={"query": "pm"})).json()["id"]
    )
    await _job_for(session_factory, user_id, search_id, "a")
    await _job_for(session_factory, user_id, search_id, "b")
    # Hidden and unlisted jobs have left the flow, so they are not "new" to look at.
    await _job_for(session_factory, user_id, search_id, "c", hidden_at=datetime.now(UTC))
    await _job_for(session_factory, user_id, search_id, "d", unlisted_at=datetime.now(UTC))
    listed = (await client.get("/api/v1/searches")).json()
    assert listed[0]["new_count"] == 2
    viewed = await client.post(f"/api/v1/searches/{search_id}/viewed")
    assert viewed.status_code == 200
    assert viewed.json()["last_viewed_at"] is not None
    assert viewed.json()["new_count"] == 0
    assert (await client.get("/api/v1/searches")).json()[0]["new_count"] == 0
    await _job_for(session_factory, user_id, search_id, "e")
    assert (await client.get("/api/v1/searches")).json()[0]["new_count"] == 1


async def test_viewed_on_an_unknown_search_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/searches/{missing}/viewed")).status_code == 404


async def test_new_counts_is_one_query_for_every_search(session: AsyncSession, user: Any) -> None:
    for name in ("a", "b", "c"):
        await searches_repo.create_search(
            session, user.id, name=name, keywords=[name], location=None, remote="include"
        )
    await session.commit()
    counts = await searches_repo.new_counts(session, user.id)
    assert len(counts) == 3 and set(counts.values()) == {0}


async def test_new_counts_never_counts_another_users_jobs_or_searches(
    session: AsyncSession, user: Any
) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    other = await get_or_create_user(session, "other@example.com")
    await session.commit()

    mine = await searches_repo.create_search(
        session, user.id, name="mine", keywords=["mine"], location=None, remote="include"
    )
    theirs = await searches_repo.create_search(
        session, other.id, name="theirs", keywords=["theirs"], location=None, remote="include"
    )
    await session.commit()

    # Both users have a job discovered after their own (never-set) last_viewed_at.
    await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id="mine-1",
        company="ExampleCo",
        title="Program Manager",
        location=None,
        url="https://example.com/mine-1",
        jd_text="x" * 80,
        posted_at=None,
        identity_hash="h-mine-1",
        repost_of=None,
        search_id=mine.id,
    )
    await jobs_repo.create_discovered_job(
        session,
        other.id,
        source="themuse",
        external_id="theirs-1",
        company="ExampleCo",
        title="Program Manager",
        location=None,
        url="https://example.com/theirs-1",
        jd_text="x" * 80,
        posted_at=None,
        identity_hash="h-theirs-1",
        repost_of=None,
        search_id=theirs.id,
    )
    await session.commit()

    counts = await searches_repo.new_counts(session, user.id)
    # If the other user's job or search leaked in, "mine" would read 2 or "theirs" would appear.
    assert counts == {mine.id: 1}


async def test_viewed_on_another_users_search_is_404_and_leaves_it_untouched(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        other = await get_or_create_user(session, "other@example.com")
        theirs = await searches_repo.create_search(
            session, other.id, name="theirs", keywords=["theirs"], location=None, remote="include"
        )
        await session.commit()
        other_id, their_search_id = other.id, theirs.id

    response = await client.post(f"/api/v1/searches/{their_search_id}/viewed")
    assert response.status_code == 404

    async with session_factory() as session:
        reloaded = await searches_repo.get_search(session, other_id, their_search_id)
        assert reloaded is not None
        assert reloaded.last_viewed_at is None
