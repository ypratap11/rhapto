from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from rhapto.api.deps import (
    AppState,
    current_user,
    get_enqueuer,
    get_event_bus,
    get_session,
    get_state,
)
from rhapto.api.errors import not_found
from rhapto.api.schemas import TailorBody, TaskOut
from rhapto.db.models import Task
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.profile import get_track
from rhapto.services.enqueue import Enqueuer
from rhapto.services.eventbus import EventBus, task_channel

router = APIRouter()
FINISHED = {"succeeded", "failed"}

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
StateDep = Annotated[AppState, Depends(get_state)]


def task_to_out(row: Task) -> TaskOut:
    return TaskOut(
        id=row.id,
        type=row.type,
        status=row.status,
        progress=dict(row.progress_json),
        error=row.error,
        result_ref=row.result_ref,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


@router.post("/jobs/{job_id}/tailor", response_model=TaskOut, status_code=202)
async def tailor_job_endpoint(
    job_id: uuid.UUID,
    body: TailorBody,
    user_id: UserDep,
    session: SessionDep,
    enqueuer: EnqueuerDep,
) -> TaskOut:
    if await job_repo.get_job(session, user_id, job_id) is None:
        raise not_found("job", job_id)
    if body.track_id is not None and await get_track(session, user_id, body.track_id) is None:
        raise HTTPException(status_code=422, detail=f"unknown track {body.track_id!r}")
    if body.parent_package_id is not None:
        parent = await package_repo.get_package(session, user_id, body.parent_package_id)
        if parent is None or parent.job_id != job_id:
            raise not_found("package", body.parent_package_id)
    request = {
        "job_id": str(job_id),
        "track_id": body.track_id,
        "feedback": body.feedback,
        "parent_package_id": str(body.parent_package_id) if body.parent_package_id else None,
    }
    task = await task_repo.create_task(session, user_id, "tailor_job", {"request": request})
    await session.commit()  # the worker (inline or arq) must see the row
    task_id = task.id
    await enqueuer.enqueue("tailor_job", task_id=str(task_id))
    session.expire_all()
    refreshed = await task_repo.get_task(session, user_id, task_id)
    assert refreshed is not None
    return task_to_out(refreshed)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> TaskOut:
    task = await task_repo.get_task(session, user_id, task_id)
    if task is None:
        raise not_found("task", task_id)
    return task_to_out(task)


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: uuid.UUID,
    user_id: UserDep,
    session: SessionDep,
    bus: EventBusDep,
    state: StateDep,
) -> EventSourceResponse:
    task = await task_repo.get_task(session, user_id, task_id)
    if task is None:
        raise not_found("task", task_id)

    async def stream() -> AsyncIterator[dict[str, str]]:
        async with bus.subscription(task_channel(str(task_id))) as events:
            async with state.session_factory() as fresh:
                current = await task_repo.get_task(fresh, user_id, task_id)
            assert current is not None
            yield {"event": "state", "data": task_to_out(current).model_dump_json()}
            if current.status in FINISHED:
                return
            async for event in events:
                yield {"event": str(event.get("event", "message")), "data": json.dumps(event)}
                if event.get("event") in {"done", "error"}:
                    return

    # sse-starlette defaults to "\r\n" line endings; use "\n" so plain-"\n\n"
    # SSE block parsing (ours and typical browser EventSource clients) works.
    return EventSourceResponse(stream(), sep="\n")
