from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_fetch_text, get_session, get_storage
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import JobCreate, JobOut, JobScoreOut, PackageSummary
from rhapto.db.models import Application, Job, JobScore, Package
from rhapto.db.repositories import jobs as repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories.discovery import scores_for_jobs
from rhapto.models.jd_extract import JDExtract
from rhapto.services.enqueue import Enqueuer
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage

router = APIRouter(prefix="/jobs")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
FetchTextDep = Annotated[FetchText, Depends(get_fetch_text)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


def job_to_out(
    job: Job,
    latest: Package | None,
    application: Application | None,
    scores: list[JobScore],
    min_fit: int | None,
) -> JobOut:
    bucket: Literal["fit", "low"] | None
    if job.best_fit is None:
        bucket = None
    elif job.rescued or (min_fit is not None and job.best_fit >= min_fit):
        bucket = "fit"
    else:
        bucket = "low"
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
        best_track_id=job.best_track_id,
        best_fit=job.best_fit,
        bucket=bucket,
        rescued=job.rescued,
        repost_of=job.repost_of,
        posted_at=job.posted_at,
        scores=[
            JobScoreOut(track_id=s.track_id, fit_score=s.fit_score, rationale=s.rationale_json)
            for s in scores
        ],
    )


async def _min_fit_for(
    session: AsyncSession, user_id: uuid.UUID, track_id: str | None
) -> int | None:
    if track_id is None:
        return None
    track = await profile_repo.get_track(session, user_id, track_id)
    return track.min_fit if track is not None else None


async def _out(session: AsyncSession, user_id: uuid.UUID, job: Job) -> JobOut:
    scores = (await scores_for_jobs(session, user_id, [job.id])).get(job.id, [])
    min_fit = await _min_fit_for(session, user_id, job.best_track_id)
    return job_to_out(
        job,
        await repo.latest_package(session, user_id, job.id),
        await repo.application_for_job(session, user_id, job.id),
        scores,
        min_fit,
    )


async def _outs(session: AsyncSession, user_id: uuid.UUID, jobs: list[Job]) -> list[JobOut]:
    scores_by_job = await scores_for_jobs(session, user_id, [j.id for j in jobs])
    tracks = {t.track_id: t.min_fit for t in await profile_repo.list_tracks(session, user_id)}
    out = []
    for job in jobs:
        out.append(
            job_to_out(
                job,
                await repo.latest_package(session, user_id, job.id),
                await repo.application_for_job(session, user_id, job.id),
                scores_by_job.get(job.id, []),
                tracks.get(job.best_track_id) if job.best_track_id else None,
            )
        )
    return out


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
    enqueuer: EnqueuerDep,
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
    job_id = job.id
    await enqueuer.enqueue("score_jobs", user_id=str(user_id), job_ids=[str(job_id)])
    session.expire_all()
    refreshed = await repo.get_job(session, user_id, job_id)
    if refreshed is None:  # committed above, so this cannot happen without a concurrent delete
        raise RuntimeError(f"job {job_id} vanished after commit")
    return await _out(session, user_id, refreshed)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    user_id: UserDep,
    session: SessionDep,
    search: str | None = Query(default=None),
    track: str | None = Query(default=None),
    bucket: Literal["fit", "low"] | None = Query(default=None),
    sort: Literal["fit", "newest"] = Query(default="fit"),
) -> list[JobOut]:
    jobs = await repo.list_jobs(
        session, user_id, search=search, track=track, bucket=bucket, sort=sort
    )
    return await _outs(session, user_id, jobs)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    return await _out(session, user_id, job)


@router.post("/{job_id}/rescue", response_model=JobOut)
async def rescue_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_rescued(job, True)
    await session.commit()
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
