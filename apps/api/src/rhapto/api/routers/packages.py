from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session, get_storage
from rhapto.api.errors import not_found
from rhapto.api.schemas import PackageOut, PackagePatch
from rhapto.db.models import Package
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as repo
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument
from rhapto.services.enqueue import Enqueuer
from rhapto.services.packaging import persist_package
from rhapto.services.profile_sync import load_profile_from_db
from rhapto.services.storage import PackageStorage

router = APIRouter()
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA = "application/pdf"
GUARDRAIL_HEADER = "X-Rhapto-Guardrails"
BLOCKED_NOTE = "GUARDRAILS-BLOCKED.md"

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


def package_to_out(row: Package) -> PackageOut:
    return PackageOut(
        id=row.id,
        job_id=row.job_id,
        track_id=row.track_id,
        version=row.version,
        status=row.status,
        resume=ResumeDocument.model_validate(row.resume_json),
        cover_note=row.cover_note,
        change_log=row.change_log,
        answers=dict(row.answers_json),
        guardrail_report=GuardrailReport.model_validate(row.guardrail_report_json),
        jd_extract=JDExtract.model_validate(row.jd_extract_json),
        llm_calls=row.llm_calls,
        parent_package_id=row.parent_package_id,
        has_docx=row.docx_path is not None,
        has_pdf=row.pdf_path is not None,
        created_at=row.created_at,
    )


def blocked_note(report: GuardrailReport) -> str:
    """Summary dropped into the zip so a blocked draft cannot be mistaken for a clean one."""
    lines = [
        "# Guardrails blocked this package",
        "",
        "Rhapto's guardrails rejected this draft. The files are still here so you can see why,",
        "but do not send this resume until every violation below is resolved.",
        "",
    ]
    for violation in report.violations:
        lines.append(
            f"- **{violation.rule}** ({violation.severity}) at `{violation.path}`: {violation.message}"
        )
    return "\n".join(lines) + "\n"


async def _get_package(session: AsyncSession, user_id: uuid.UUID, package_id: uuid.UUID) -> Package:
    row = await repo.get_package(session, user_id, package_id)
    if row is None:
        raise not_found("package", package_id)
    return row


@router.get("/jobs/{job_id}/packages", response_model=list[PackageOut])
async def list_packages(
    job_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> list[PackageOut]:
    if await job_repo.get_job(session, user_id, job_id) is None:
        raise not_found("job", job_id)
    rows = await repo.list_packages_for_job(session, user_id, job_id)
    return [package_to_out(row) for row in rows]


@router.get("/packages/{package_id}", response_model=PackageOut)
async def get_package(package_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> PackageOut:
    return package_to_out(await _get_package(session, user_id, package_id))


@router.patch(
    "/packages/{package_id}",
    response_model=PackageOut,
    status_code=201,
    responses={
        201: {
            "description": "A new package version was created",
            "headers": {
                "Location": {
                    "description": "URL of the newly created package version",
                    "schema": {"type": "string", "format": "uri"},
                }
            },
        }
    },
)
async def patch_package(
    package_id: uuid.UUID,
    body: PackagePatch,
    request: Request,
    response: Response,
    user_id: UserDep,
    session: SessionDep,
    storage: StorageDep,
    enqueuer: EnqueuerDep,
) -> PackageOut:
    """Edited resume -> re-validate with the stored selection -> re-render -> new version.

    Never bypasses guardrails: the edited resume is re-run through run_guardrails with the
    parent's stored selection and job's cover note before it is persisted as a new version.
    """
    parent = await _get_package(session, user_id, package_id)
    job = await job_repo.get_job(session, user_id, parent.job_id)
    if job is None:
        raise not_found("job", parent.job_id)
    profile = await load_profile_from_db(session, user_id)
    extract = JDExtract.model_validate(parent.jd_extract_json)
    report = run_guardrails(
        body.resume, profile, parent.selection_block_ids, extract, cover_note=parent.cover_note
    )
    try:
        # python-docx builds a zip in memory; keep it off the event loop with the rest of the IO.
        docx = await asyncio.to_thread(render_docx, body.resume, profile.block_map())
    except OrphanBulletError:
        docx = b""

    model = repo.package_row_to_model(
        parent,
        job_company=job.company or extract.company,
        job_title=job.title or extract.title,
        jd_text=job.jd_text,
        url=job.url,
        location=job.location,
    )
    model = model.model_copy(
        update={
            "resume": body.resume,
            "guardrail_report": report,
            "status": "draft" if report.passed else "blocked",
            "llm_calls": 0,
        }
    )
    row = await persist_package(
        session,
        user_id=user_id,
        job=job,
        package=model,
        selection_block_ids=list(parent.selection_block_ids),
        parent_package_id=parent.id,
        storage=storage,
        docx=docx,
    )
    # PDF rendering needs LibreOffice, which lives on the worker, not the slim api image.
    await enqueuer.enqueue("render_package_pdf", package_id=str(row.id))
    response.headers["Location"] = str(request.url_for("get_package", package_id=row.id))
    return package_to_out(row)


@router.get("/packages/{package_id}/download")
async def download_package(
    package_id: uuid.UUID, user_id: UserDep, session: SessionDep, storage: StorageDep
) -> Response:
    row = await _get_package(session, user_id, package_id)
    job = await job_repo.get_job(session, user_id, row.job_id)
    if job is None:
        raise not_found("job", row.job_id)
    model = repo.package_row_to_model(
        row,
        job_company=job.company or "",
        job_title=job.title or "",
        jd_text=job.jd_text,
        url=job.url,
        location=job.location,
    )
    passed = model.guardrail_report.passed
    extra_files = {} if passed else {BLOCKED_NOTE: blocked_note(model.guardrail_report)}
    data = await asyncio.to_thread(
        storage.build_zip,
        str(row.id),
        row.cover_note,
        model.model_dump_json(indent=2),
        extra_files,
    )
    filename = f"rhapto-package-v{row.version}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            GUARDRAIL_HEADER: "passed" if passed else "blocked",
        },
    )


@router.get("/packages/{package_id}/files/{name}")
async def package_file(
    package_id: uuid.UUID, name: str, user_id: UserDep, session: SessionDep, storage: StorageDep
) -> FileResponse:
    if name not in ("resume.docx", "resume.pdf"):
        raise HTTPException(status_code=422, detail="name must be resume.docx or resume.pdf")
    row = await _get_package(session, user_id, package_id)
    path = storage.path_for(str(row.id), name)  # type: ignore[arg-type]
    if path is None:
        raise not_found("file", name)
    media = DOCX_MEDIA if name == "resume.docx" else PDF_MEDIA
    report = GuardrailReport.model_validate(row.guardrail_report_json)
    return FileResponse(
        path,
        media_type=media,
        filename=name,
        headers={GUARDRAIL_HEADER: "passed" if report.passed else "blocked"},
    )
