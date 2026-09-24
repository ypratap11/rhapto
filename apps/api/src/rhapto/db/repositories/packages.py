from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import APPLICATION_STATUSES, APPLIED_STATUSES, Application, Job, Package
from rhapto.models.package import ApplicationPackage

NOT_APPLIED_STATUSES = tuple(s for s in APPLICATION_STATUSES if s not in APPLIED_STATUSES)


async def next_version(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(Package.version)).where(
            Package.user_id == user_id, Package.job_id == job_id
        )
    )
    return (current or 0) + 1


async def create_package(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    package: ApplicationPackage,
    *,
    selection_block_ids: list[str],
    parent_package_id: uuid.UUID | None,
    docx_path: str | None,
    pdf_path: str | None,
) -> Package:
    row = Package(
        user_id=user_id,
        job_id=job_id,
        track_id=package.track_id,
        version=package.version,
        status=package.status,
        resume_json=package.resume.model_dump(mode="json"),
        cover_note=package.cover_note,
        change_log=package.change_log,
        answers_json=dict(package.answers),
        guardrail_report_json=package.guardrail_report.model_dump(mode="json"),
        jd_extract_json=package.jd_extract.model_dump(mode="json"),
        selection_block_ids=list(selection_block_ids),
        llm_calls=package.llm_calls,
        input_tokens=package.usage.input_tokens,
        output_tokens=package.usage.output_tokens,
        cache_read_tokens=package.usage.cache_read_input_tokens,
        cache_creation_tokens=package.usage.cache_creation_input_tokens,
        llm_model=package.model,
        docx_path=docx_path,
        pdf_path=pdf_path,
        parent_package_id=parent_package_id,
        mode=package.mode,
        edits_json=[e.model_dump(mode="json") for e in package.edits],
        source_document_json=(
            package.source_document.model_dump(mode="json") if package.source_document else None
        ),
    )
    session.add(row)
    await session.flush()
    return row


async def get_package(
    session: AsyncSession, user_id: uuid.UUID, package_id: uuid.UUID
) -> Package | None:
    result: Package | None = await session.scalar(
        select(Package).where(Package.user_id == user_id, Package.id == package_id)
    )
    return result


async def list_packages_for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> list[Package]:
    return list(
        await session.scalars(
            select(Package)
            .where(Package.user_id == user_id, Package.job_id == job_id)
            .order_by(Package.version)
        )
    )


def set_archived(package: Package, archived: bool) -> None:
    if archived:
        package.archived_at = package.archived_at or datetime.now(UTC)
    else:
        package.archived_at = None


def set_status(package: Package, status: str) -> None:
    """Promote or demote a package between draft and ready. Nothing else on the row changes."""
    package.status = status


async def list_packages(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    applied: bool | None = None,
    archived: bool = False,
) -> list[tuple[Package, Job, Application | None]]:
    """Latest package per job, newest first, with its job and application (if any).

    `archived=False` is the Resumes queue: it drops archived packages and packages whose job the
    user hid or a source stopped listing, because none of those have a next step any more.
    `archived=True` is the archive view and shows only archived packages.
    """
    latest = (
        select(Package.job_id, func.max(Package.version).label("version"))
        .where(Package.user_id == user_id)
        .group_by(Package.job_id)
        .subquery()
    )
    query = (
        select(Package, Job, Application)
        .join(latest, and_(Package.job_id == latest.c.job_id, Package.version == latest.c.version))
        .join(Job, Job.id == Package.job_id)
        .outerjoin(
            Application,
            and_(Application.job_id == Package.job_id, Application.user_id == user_id),
        )
        .where(Package.user_id == user_id)
        .order_by(Package.created_at.desc(), Package.id)
    )
    if archived:
        query = query.where(Package.archived_at.is_not(None))
    else:
        query = query.where(
            Package.archived_at.is_(None), Job.hidden_at.is_(None), Job.unlisted_at.is_(None)
        )
    if status:
        query = query.where(Package.status == status)
    if applied is True:
        query = query.where(Application.status.in_(APPLIED_STATUSES))
    elif applied is False:
        query = query.where(
            or_(Application.id.is_(None), Application.status.in_(NOT_APPLIED_STATUSES))
        )
    return [(p, j, a) for p, j, a in (await session.execute(query)).all()]


def package_row_to_model(
    row: Package,
    *,
    job_company: str,
    job_title: str,
    jd_text: str,
    url: str | None = None,
    location: str | None = None,
) -> ApplicationPackage:
    return ApplicationPackage.model_validate(
        {
            "job": {
                "company": job_company,
                "title": job_title,
                "location": location,
                "url": url,
                "jd_text": jd_text,
            },
            "track_id": row.track_id,
            "jd_extract": row.jd_extract_json,
            "resume": row.resume_json,
            "cover_note": row.cover_note,
            "change_log": row.change_log,
            "answers": row.answers_json,
            "guardrail_report": row.guardrail_report_json,
            "version": row.version,
            "status": row.status,
            "llm_calls": row.llm_calls,
            "usage": {
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cache_read_input_tokens": row.cache_read_tokens,
                "cache_creation_input_tokens": row.cache_creation_tokens,
            },
            "model": row.llm_model,
            "created_at": row.created_at,
            # Rows written before tune mode existed have NULL here; the defaults keep them
            # readable as what they were -- a blocks-mode package with no document.
            "mode": row.mode or "blocks",
            "edits": row.edits_json or [],
            "source_document": row.source_document_json,
        }
    )


@dataclass(frozen=True)
class ModelUsageRow:
    """One llm_model's totals across some set of packages (NULL model is its own group).

    Raw sums only -- no pricing here. `rhapto.services.usage` prices each group at its own
    model's rate and adds the results, because pricing the sum of tokens across models at one
    rate would misreport as soon as a user switches models.
    """

    model: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


async def usage_by_model(
    session: AsyncSession, user_id: uuid.UUID, *, since: datetime | None = None
) -> list[ModelUsageRow]:
    """Token totals for this user, grouped by the model that produced them."""
    query = (
        select(
            Package.llm_model,
            func.coalesce(func.sum(Package.llm_calls), 0),
            func.coalesce(func.sum(Package.input_tokens), 0),
            func.coalesce(func.sum(Package.output_tokens), 0),
            func.coalesce(func.sum(Package.cache_read_tokens), 0),
            func.coalesce(func.sum(Package.cache_creation_tokens), 0),
        )
        .where(Package.user_id == user_id)
        .group_by(Package.llm_model)
    )
    if since is not None:
        query = query.where(Package.created_at >= since)
    rows = (await session.execute(query)).all()
    return [
        ModelUsageRow(
            model=model,
            calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        )
        for (
            model,
            calls,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_creation_tokens,
        ) in rows
    ]


@dataclass(frozen=True)
class RecentPackageUsage:
    package_id: uuid.UUID
    job_id: uuid.UUID
    company: str | None
    job_title: str | None
    model: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    created_at: datetime


async def recent_usage(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 20
) -> list[RecentPackageUsage]:
    """The most recent packages with their job, newest first, for the Settings usage table."""
    query = (
        select(Package, Job.company, Job.title)
        .join(Job, Job.id == Package.job_id)
        .where(Package.user_id == user_id)
        .order_by(Package.created_at.desc(), Package.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    return [
        RecentPackageUsage(
            package_id=package.id,
            job_id=package.job_id,
            company=company,
            job_title=title,
            model=package.llm_model,
            calls=package.llm_calls,
            input_tokens=package.input_tokens,
            output_tokens=package.output_tokens,
            cache_read_tokens=package.cache_read_tokens,
            cache_creation_tokens=package.cache_creation_tokens,
            created_at=package.created_at,
        )
        for package, company, title in rows
    ]
