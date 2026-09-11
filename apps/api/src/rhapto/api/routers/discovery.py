from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session
from rhapto.api.routers.tailor import task_to_out
from rhapto.api.schemas import PollRunOut, SourceInfoOut, TaskOut
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.services.discovery.sources import all_sources
from rhapto.services.enqueue import Enqueuer

router = APIRouter(prefix="/discovery")
UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


@router.post("/poll", response_model=TaskOut, status_code=202)
async def poll(user_id: UserDep, session: SessionDep, enqueuer: EnqueuerDep) -> TaskOut:
    task = await task_repo.create_task(session, user_id, "poll_now", {})
    await session.commit()
    task_id = task.id
    await enqueuer.enqueue("poll_now", task_id=str(task_id))
    session.expire_all()
    refreshed = await task_repo.get_task(session, user_id, task_id)
    if refreshed is None:
        raise RuntimeError(f"task {task_id} vanished after commit")
    return task_to_out(refreshed)


@router.get("/runs", response_model=list[PollRunOut])
async def runs(user_id: UserDep, session: SessionDep) -> list[PollRunOut]:
    return [
        PollRunOut.model_validate(r, from_attributes=True)
        for r in await disc_repo.latest_runs(session, user_id)
    ]


@router.get("/sources", response_model=list[SourceInfoOut])
async def sources(user_id: UserDep) -> list[SourceInfoOut]:
    return [
        SourceInfoOut(name=i.name, kind=i.kind, label=i.label, needs_board=i.needs_board)
        for i in all_sources()
    ]
