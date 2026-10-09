"""GET /api/v1/coach/readiness: a per-user fact about one track."""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.scoring import rescore_user

URL = "/api/v1/coach/readiness"
TRACK = Track(
    id="tpm",
    name="TPM",
    resume_base="b",
    min_fit=60,
    keywords=["roadmap", "launch"],
    description="Program leadership",
)


async def test_a_saved_track_is_not_ready_until_a_rescore_has_finished(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as s:
        await profile_repo.upsert_track(s, user_id, TRACK)
        await s.commit()
    assert (await client.get(URL, params={"track": "tpm"})).json() == {"ready": False}
    async with session_factory() as s:
        await rescore_user(s, user_id, FakeEmbeddingProvider(dimensions=384))
        await s.commit()
    assert (await client.get(URL, params={"track": "tpm"})).json() == {"ready": True}


async def test_an_unknown_track_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get(URL, params={"track": "nope"})).status_code == 404


async def test_readiness_of_another_users_track_is_404(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as s:
        other = await get_or_create_user(s, "someone-else@example.com")
        await profile_repo.upsert_track(s, other.id, TRACK)
        await s.commit()
    assert (await client.get(URL, params={"track": "tpm"})).status_code == 404


async def test_the_track_parameter_is_required(client: httpx.AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 422


async def test_unauthenticated_is_401(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get(URL, params={"track": "tpm"})).status_code == 401
