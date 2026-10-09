"""POST /api/v1/coach/events: counts only, self-only, idempotent per (user, step, UTC day)."""

from __future__ import annotations

import uuid
from typing import get_args

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.schemas import CoachStep
from rhapto.db.models import COACH_STEPS, CoachEvent
from rhapto.db.repositories.users import get_or_create_user

URL = "/api/v1/coach/events"


async def _count(session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> int:
    async with session_factory() as session:
        return int(
            await session.scalar(
                select(func.count()).select_from(CoachEvent).where(CoachEvent.user_id == user_id)
            )
            or 0
        )


def test_the_literal_mirrors_the_check_tuple() -> None:
    """A typo returns 422 only if the Literal and the CHECK agree. They are defined twice (the
    models module cannot import the API), so this is the one place that holds them together."""
    assert set(get_args(CoachStep)) == set(COACH_STEPS)


@pytest.mark.parametrize("step", COACH_STEPS)
async def test_each_step_records_a_row_and_returns_204(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    step: str,
) -> None:
    response = await client.post(URL, json={"step": step})
    assert response.status_code == 204 and response.content == b""
    assert await _count(session_factory, user_id) == 1


async def test_the_same_step_twice_on_one_day_is_one_row_and_still_204(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    assert (await client.post(URL, json={"step": "started"})).status_code == 204
    assert (await client.post(URL, json={"step": "started"})).status_code == 204
    assert await _count(session_factory, user_id) == 1


async def test_a_typo_is_422_not_500(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json={"step": "downloded"})
    assert response.status_code == 422
    assert (await client.post(URL, json={})).status_code == 422


async def test_extra_fields_are_rejected_so_no_text_can_ride_along(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(URL, json={"step": "started", "resume_text": "Maya Chen ..."})
    assert response.status_code == 422


async def test_unauthenticated_is_401(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.post(URL, json={"step": "started"})).status_code == 401


async def test_there_is_no_read_route(client: httpx.AsyncClient) -> None:
    """The funnel script reads the table on the server; the API exposes no list/get."""
    assert (await client.get(URL)).status_code == 405


async def test_events_are_per_user(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    async with session_factory() as session:
        other = await get_or_create_user(session, "someone-else@example.com")
        await session.execute(
            text("INSERT INTO coach_events (id, user_id, step) VALUES (:id, :uid, 'started')"),
            {"id": str(uuid.uuid4()), "uid": str(other.id)},
        )
        await session.commit()
    # The authenticated user has not fired 'started' yet: the other user's row does not make this
    # one a conflict, and does not count towards this user's total.
    assert (await client.post(URL, json={"step": "started"})).status_code == 204
    assert await _count(session_factory, user_id) == 1
