from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_fetch_text, get_session, get_storage
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import JobCreate, JobOut, JobScoreOut, PackageSummary
from rhapto.db.models import Application, Job, JobScore, Package
from rhapto.db.repositories import jobs as repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories.discovery import scores_for_jobs
from rhapto.engine.scoring import LocationTier
from rhapto.models.jd_extract import JDExtract
from rhapto.services.enqueue import Enqueuer
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage
from rhapto.services.taxonomy import find_field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
FetchTextDep = Annotated[FetchText, Depends(get_fetch_text)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]

#: A refetch after a live search asks for at most LIVE_CAP jobs per source across a handful of
#: sources; 200 is generous for that and small enough to keep the IN clause sane.
MAX_IDS = 200


def parse_ids(raw: str | None) -> list[uuid.UUID] | None:
    """`?ids=a,b,c` as UUIDs. None when the parameter was not sent at all."""
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) > MAX_IDS:
        raise HTTPException(status_code=422, detail=f"ids accepts at most {MAX_IDS} values")
    try:
        return [uuid.UUID(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"ids contains a value that is not a UUID: {exc}"
        ) from exc


def parse_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def job_to_out(
    job: Job,
    latest: Package | None,
    application: Application | None,
    scores: list[JobScore],
    min_fit: int | None,
    search_name: str | None = None,
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
                mode="tune" if latest.mode == "tune" else "blocks",
                created_at=latest.created_at,
            )
            if latest
            else None
        ),
        application_status=application.status if application else None,
        best_track_id=job.best_track_id,
        best_fit=job.best_fit,
        bucket=bucket,
        location_tier=cast("LocationTier | None", job.location_tier),
        rescued=job.rescued,
        repost_of=job.repost_of,
        posted_at=job.posted_at,
        scores=[
            JobScoreOut(track_id=s.track_id, fit_score=s.fit_score, rationale=s.rationale_json)
            for s in scores
        ],
        search_name=search_name,
        salary_text=job.salary_text,
        hidden_at=job.hidden_at,
        unlisted_at=job.unlisted_at,
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
    search_name = await repo.search_name_for(session, user_id, job.search_id)
    return job_to_out(
        job,
        await repo.latest_package(session, user_id, job.id),
        await repo.application_for_job(session, user_id, job.id),
        scores,
        min_fit,
        search_name,
    )


async def _outs(
    session: AsyncSession, user_id: uuid.UUID, jobs: list[tuple[Job, str | None]]
) -> list[JobOut]:
    scores_by_job = await scores_for_jobs(session, user_id, [j.id for j, _ in jobs])
    tracks = {t.track_id: t.min_fit for t in await profile_repo.list_tracks(session, user_id)}
    out = []
    for job, search_name in jobs:
        out.append(
            job_to_out(
                job,
                await repo.latest_package(session, user_id, job.id),
                await repo.application_for_job(session, user_id, job.id),
                scores_by_job.get(job.id, []),
                tracks.get(job.best_track_id) if job.best_track_id else None,
                search_name,
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
    try:
        await enqueuer.enqueue("score_jobs", user_id=str(user_id), job_ids=[str(job_id)])
    except Exception:  # the row is committed; a queue outage must not fail the request
        logger.exception(
            "could not enqueue %s; the record is saved but not (re)scored", "score_jobs"
        )
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
    region: Literal["preferred", "us", "any"] = Query(default="any"),
    sort: Literal["fit", "newest"] = Query(default="newest"),
    ids: str | None = Query(default=None, description="comma-separated job ids, at most 200"),
    hidden: bool = Query(default=False, description="show only hidden jobs"),
    search_id: Annotated[uuid.UUID | None, Query()] = None,
    posted_within: Literal["24h", "7d", "30d", "90d", "any"] = Query(default="90d"),
    sources: str | None = Query(default=None, description="comma-separated source ids"),
    field: str | None = Query(default=None, description="taxonomy field id"),
    recommended: bool = Query(
        default=False,
        description="only jobs with no resume, no application, not hidden and not unlisted",
    ),
) -> list[JobOut]:
    track_ids: list[str] | None = None
    if field is not None:
        if find_field(field) is None:
            raise HTTPException(status_code=422, detail=f"unknown taxonomy field {field!r}")
        track_ids = [
            t.track_id for t in await profile_repo.list_tracks(session, user_id) if t.field == field
        ]
    rows = await repo.list_jobs(
        session,
        user_id,
        search=search,
        track=track,
        bucket=bucket,
        region=region,
        sort=sort,
        ids=parse_ids(ids),
        hidden=hidden,
        search_id=search_id,
        posted_within=posted_within,
        sources=parse_csv(sources),
        track_ids=track_ids,
        recommended=recommended,
    )
    return await _outs(session, user_id, rows)


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


@router.post("/{job_id}/hide", response_model=JobOut)
async def hide_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    """ "Not interested": the job leaves the grid, recommendations and the Resumes queue."""
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_hidden(job, True)
    await session.commit()
    return await _out(session, user_id, job)


@router.post("/{job_id}/unhide", response_model=JobOut)
async def unhide_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    """Undo, from the toast or the "Show hidden" view."""
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_hidden(job, False)
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
