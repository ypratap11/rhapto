"""Coach support endpoints. `GET /coach/readiness` is read-only and per user; `POST /coach/events`
records counts only."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.errors import not_found
from rhapto.api.schemas import CoachEventIn, ReadinessOut
from rhapto.db.repositories import coach as coach_repo
from rhapto.db.repositories import profile as profile_repo

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/coach/readiness", response_model=ReadinessOut)
async def coach_readiness(
    track: Annotated[str, Query(min_length=1)], user_id: UserDep, session: SessionDep
) -> ReadinessOut:
    """Has the latest save of this track been covered by a rescore that finished? The coach waits on
    this, not on scores: a rescore commits every SCORE_CHUNK jobs, so scores appear long before it ends."""
    ready = await profile_repo.track_readiness(session, user_id, track)
    if ready is None:
        raise not_found("track", track)
    return ReadinessOut(ready=ready)


@router.post("/coach/events", status_code=204)
async def record_coach_event(body: CoachEventIn, user_id: UserDep, session: SessionDep) -> Response:
    await coach_repo.record_event(session, user_id, body.step)
    await session.commit()
    return Response(status_code=204)
