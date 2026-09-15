from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.errors import not_found
from rhapto.api.schemas import SearchIn, SearchOut
from rhapto.db.models import SearchRow
from rhapto.db.repositories import searches as repo
from rhapto.services.discovery.search import derive_searches

router = APIRouter(prefix="/searches")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def search_to_out(row: SearchRow) -> SearchOut:
    return SearchOut(
        id=row.id,
        name=row.name,
        keywords=list(row.keywords),
        location=row.location,
        remote=row.remote,
        active=row.active,
        derived_from_track_id=row.derived_from_track_id,
        created_at=row.created_at,
    )


@router.get("", response_model=list[SearchOut])
async def list_searches(user_id: UserDep, session: SessionDep) -> list[SearchOut]:
    return [search_to_out(r) for r in await repo.list_searches(session, user_id)]


@router.post("", response_model=SearchOut, status_code=201)
async def create_search(body: SearchIn, user_id: UserDep, session: SessionDep) -> SearchOut:
    row = await repo.create_search(
        session,
        user_id,
        name=body.name,
        keywords=body.keywords,
        location=body.location,
        remote=body.remote,
        active=body.active,
    )
    await session.commit()
    return search_to_out(row)


@router.post("/derive", response_model=list[SearchOut])
async def derive(user_id: UserDep, session: SessionDep) -> list[SearchOut]:
    created = await derive_searches(session, user_id)
    await session.commit()
    return [search_to_out(r) for r in created]


@router.put("/{search_id}", response_model=SearchOut)
async def update_search(
    search_id: uuid.UUID, body: SearchIn, user_id: UserDep, session: SessionDep
) -> SearchOut:
    row = await repo.get_search(session, user_id, search_id)
    if row is None:
        raise not_found("search", search_id)
    await repo.update_search(
        session,
        row,
        name=body.name,
        keywords=body.keywords,
        location=body.location,
        remote=body.remote,
        active=body.active,
    )
    await session.commit()
    return search_to_out(row)


@router.delete("/{search_id}", status_code=204)
async def delete_search(search_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> Response:
    if not await repo.delete_search(session, user_id, search_id):
        raise not_found("search", search_id)
    await session.commit()
    return Response(status_code=204)
