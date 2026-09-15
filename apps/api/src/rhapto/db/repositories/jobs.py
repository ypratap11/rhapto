from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, and_, delete, func, not_, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Application, Job, Package, SearchRow, Track

compute_dedupe_hash = dedupe_hash


async def create_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    jd_text: str,
    source: str = "manual",
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    url: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id,
        source=source,
        company=company,
        title=title,
        location=location,
        url=url,
        jd_text=jd_text,
        dedupe_hash=compute_dedupe_hash(jd_text),
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


async def find_duplicate(
    session: AsyncSession, user_id: uuid.UUID, dedupe_hash_value: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.dedupe_hash == dedupe_hash_value)
    )
    return result


async def list_jobs(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    search: str | None = None,
    track: str | None = None,
    bucket: str | None = None,
    region: str = "any",
    sort: str = "fit",
) -> list[tuple[Job, str | None]]:
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    query = (
        select(Job, SearchRow.name)
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .outerjoin(SearchRow, SearchRow.id == Job.search_id)
        .where(Job.user_id == user_id)
    )
    if search:
        # Escape LIKE metacharacters so a search for "100%" is a literal, not a wildcard.
        escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                Job.company.ilike(pattern, escape="\\"),
                Job.title.ilike(pattern, escape="\\"),
                Job.jd_text.ilike(pattern, escape="\\"),
            )
        )
    if track:
        query = query.where(Job.best_track_id == track)
    # `location_tier` is NULL on rows scored before location priority shipped and on rows the
    # scorer has not reached; those read as "unknown", so they stay visible under "us" and
    # only the deliberately narrow "preferred" filter hides them.
    tier = func.coalesce(Job.location_tier, "unknown")
    if region == "preferred":
        query = query.where(tier == "preferred")
    elif region == "us":
        query = query.where(tier.in_(("preferred", "remote", "country", "unknown")))
    # `best_track_id` has no FK, so a scored job whose track was deleted or renamed
    # outer-joins to a NULL min_fit. Coalesce to a value above any real min_fit (0-100)
    # so the comparison is always a definite boolean rather than NULL: an orphaned
    # track can never satisfy `best_fit >= min_fit` and the job counts as low fit,
    # per the brief, instead of silently vanishing from both buckets.
    min_fit = func.coalesce(tracks.c.min_fit, 101)
    fit_condition = or_(
        Job.rescued.is_(True), and_(Job.best_fit.is_not(None), Job.best_fit >= min_fit)
    )
    if bucket == "fit":
        query = query.where(
            or_(Job.best_fit.is_(None), fit_condition)
        )  # unscored jobs stay visible
    elif bucket == "low":
        query = query.where(Job.best_fit.is_not(None), not_(fit_condition))
    if sort == "newest":
        query = query.order_by(Job.discovered_at.desc(), Job.created_at.desc(), Job.id)
    else:
        query = query.order_by(nulls_last(Job.best_fit.desc()), Job.discovered_at.desc(), Job.id)
    return [(job, name) for job, name in (await session.execute(query)).all()]


async def search_name_for(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID | None
) -> str | None:
    if search_id is None:
        return None
    result: str | None = await session.scalar(
        select(SearchRow.name).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
    )
    return result


async def find_by_external_id(
    session: AsyncSession, user_id: uuid.UUID, source: str, external_id: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(
            Job.user_id == user_id, Job.source == source, Job.external_id == external_id
        )
    )
    return result


async def find_by_identity(
    session: AsyncSession, user_id: uuid.UUID, identity_hash: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job)
        .where(Job.user_id == user_id, Job.identity_hash == identity_hash)
        .order_by(Job.discovered_at)
        .limit(1)
    )
    return result


async def create_discovered_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: str,
    external_id: str,
    company: str,
    title: str,
    location: str | None,
    url: str,
    jd_text: str,
    posted_at: datetime | None,
    identity_hash: str,
    repost_of: uuid.UUID | None,
    search_id: uuid.UUID | None = None,
    salary_text: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id,
        source=source,
        external_id=external_id,
        company=company,
        title=title,
        location=location,
        url=url,
        jd_text=jd_text,
        dedupe_hash=compute_dedupe_hash(jd_text),
        discovered_at=datetime.now(UTC),
        posted_at=posted_at,
        identity_hash=identity_hash,
        repost_of=repost_of,
        search_id=search_id,
        salary_text=salary_text,
    )
    session.add(job)
    await session.flush()
    return job


def set_rescued(job: Job, value: bool) -> None:
    job.rescued = value


async def get_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.id == job_id)
    )
    return result


async def delete_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(delete(Job).where(Job.user_id == user_id, Job.id == job_id)),
    )
    return bool(result.rowcount)


async def package_ids_for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(Package.id).where(Package.user_id == user_id, Package.job_id == job_id)
        )
    )


async def latest_package(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> Package | None:
    result: Package | None = await session.scalar(
        select(Package)
        .where(Package.user_id == user_id, Package.job_id == job_id)
        .order_by(Package.version.desc())
        .limit(1)
    )
    return result


async def application_for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> Application | None:
    result: Application | None = await session.scalar(
        select(Application)
        .where(Application.user_id == user_id, Application.job_id == job_id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    return result
