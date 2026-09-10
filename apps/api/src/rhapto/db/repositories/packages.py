from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Package
from rhapto.models.package import ApplicationPackage


async def next_version(session: AsyncSession, job_id: uuid.UUID) -> int:
    current = await session.scalar(
        select(func.max(Package.version)).where(Package.job_id == job_id)
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
        docx_path=docx_path,
        pdf_path=pdf_path,
        parent_package_id=parent_package_id,
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
            "created_at": row.created_at,
        }
    )
