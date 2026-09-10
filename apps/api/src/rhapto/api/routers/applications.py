from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationPatch,
    BoardOut,
    JobRef,
    StatusChange,
)
from rhapto.db.models import APPLICATION_STATUSES, Application, Job
from rhapto.db.repositories import applications as repo
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as package_repo

router = APIRouter(prefix="/applications")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def application_to_out(row: Application, job: Job) -> ApplicationOut:
    return ApplicationOut(
        id=row.id,
        job=JobRef(id=job.id, company=job.company, title=job.title),
        package_id=row.package_id,
        status=row.status,
        applied_at=row.applied_at,
        notes=row.notes,
        status_history=[StatusChange.model_validate(h) for h in row.status_history_json],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _out(session: AsyncSession, row: Application) -> ApplicationOut:
    job = await session.get(Job, row.job_id)
    if job is None:
        raise not_found("job", row.job_id)
    return application_to_out(row, job)


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=201,
    responses={
        409: {
            "description": "This job already has an application",
            "content": {"application/problem+json": {}},
        }
    },
)
async def create_application(
    body: ApplicationCreate,
    user_id: UserDep,
    session: SessionDep,
) -> ApplicationOut | JSONResponse:
    job = await job_repo.get_job(session, user_id, body.job_id)
    if job is None:
        raise not_found("job", body.job_id)
    if body.package_id is not None:
        package = await package_repo.get_package(session, user_id, body.package_id)
        if package is None or package.job_id != job.id:
            raise not_found("package", body.package_id)
    existing = await job_repo.application_for_job(session, user_id, job.id)
    if existing is not None:
        return problem(
            409,
            "Conflict",
            "this job already has an application",
            existing_application_id=str(existing.id),
        )
    row = await repo.create_application(session, user_id, job.id, body.package_id)
    await session.commit()
    return application_to_out(row, job)


@router.get("", response_model=BoardOut)
async def board(user_id: UserDep, session: SessionDep) -> BoardOut:
    columns: dict[str, list[ApplicationOut]] = {status: [] for status in APPLICATION_STATUSES}
    for row in await repo.list_applications(session, user_id):
        columns.setdefault(row.status, []).append(await _out(session, row))
    return BoardOut(columns=columns)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> ApplicationOut:
    row = await repo.get_application(session, user_id, application_id)
    if row is None:
        raise not_found("application", application_id)
    return await _out(session, row)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def patch_application(
    application_id: uuid.UUID,
    body: ApplicationPatch,
    user_id: UserDep,
    session: SessionDep,
) -> ApplicationOut:
    row = await repo.get_application(session, user_id, application_id)
    if row is None:
        raise not_found("application", application_id)
    if body.status is not None:
        repo.set_status(row, body.status)
    if body.notes is not None:
        row.notes = body.notes
    await session.commit()
    await session.refresh(row)
    return await _out(session, row)


@router.delete("/{application_id}", status_code=204)
async def delete_application(
    application_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> Response:
    if not await repo.delete_application(session, user_id, application_id):
        raise not_found("application", application_id)
    await session.commit()
    return Response(status_code=204)
