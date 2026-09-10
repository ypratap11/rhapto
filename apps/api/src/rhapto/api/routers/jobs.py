from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_fetch_text, get_session, get_storage
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import JobCreate, JobOut, PackageSummary
from rhapto.db.models import Application, Job, Package
from rhapto.db.repositories import jobs as repo
from rhapto.models.jd_extract import JDExtract
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage

router = APIRouter(prefix="/jobs")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
FetchTextDep = Annotated[FetchText, Depends(get_fetch_text)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]


def job_to_out(job: Job, latest: Package | None, application: Application | None) -> JobOut:
    return JobOut(
        id=job.id,
        source=job.source,
        company=job.company,
        title=job.title,
        location=job.location,
        url=job.url,
        jd_text=job.jd_text,
        extracted=JDExtract.model_validate(job.extracted_json) if job.extracted_json else None,
        discovered_at=job.discovered_at,
        latest_package=(
            PackageSummary(
                id=latest.id,
                version=latest.version,
                status=latest.status,
                created_at=latest.created_at,
            )
            if latest
            else None
        ),
        application_status=application.status if application else None,
    )


async def _out(session: AsyncSession, user_id: uuid.UUID, job: Job) -> JobOut:
    return job_to_out(
        job,
        await repo.latest_package(session, user_id, job.id),
        await repo.application_for_job(session, user_id, job.id),
    )


@router.post(
    "",
    response_model=JobOut,
    status_code=201,
    responses={
        409: {
            "description": "A job with the same description already exists",
            "content": {"application/problem+json": {}},
        }
    },
)
async def create_job(
    body: JobCreate,
    user_id: UserDep,
    session: SessionDep,
    fetch_text: FetchTextDep,
) -> Any:
    jd_text = body.jd_text if body.jd_text is not None else await fetch_text(body.url or "")
    duplicate = await repo.find_duplicate(session, user_id, repo.compute_dedupe_hash(jd_text))
    if duplicate is not None:
        return problem(
            409,
            "Conflict",
            "a job with the same description already exists",
            existing_job_id=str(duplicate.id),
        )
    job = await repo.create_job(
        session,
        user_id,
        jd_text=jd_text,
        company=body.company,
        title=body.title,
        location=body.location,
        url=body.url,
    )
    await session.commit()
    return await _out(session, user_id, job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    user_id: UserDep,
    session: SessionDep,
    search: str | None = Query(default=None),
) -> list[JobOut]:
    return [
        await _out(session, user_id, job)
        for job in await repo.list_jobs(session, user_id, search=search)
    ]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    return await _out(session, user_id, job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    user_id: UserDep,
    session: SessionDep,
    storage: StorageDep,
) -> Response:
    package_ids = await repo.package_ids_for_job(session, user_id, job_id)
    if not await repo.delete_job(session, user_id, job_id):
        raise not_found("job", job_id)
    await session.commit()
    for package_id in package_ids:
        storage.delete(str(package_id))
    return Response(status_code=204)
