from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any, Literal, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session, get_storage
from rhapto.api.errors import not_found
from rhapto.api.schemas import EditPatch, PackageListItem, PackageOut, PackagePatch
from rhapto.db.models import Package
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.compose import build_header
from rhapto.engine.document import apply_edits, to_resume_document
from rhapto.engine.guardrails.registry import remedies_for, run_guardrails
from rhapto.engine.guardrails.tune import run_tune_guardrails
from rhapto.engine.providers.llm import TokenUsage
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.engine.render.tune_docx import render_tuned_docx
from rhapto.engine.types import EngineError, Profile
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument
from rhapto.models.source_document import Edit, SourceDocument
from rhapto.services.documents import load_source
from rhapto.services.enqueue import Enqueuer
from rhapto.services.naming import download_basename
from rhapto.services.packaging import persist_package
from rhapto.services.pricing import estimate_cost
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
    cost = estimate_cost(
        row.llm_model,
        TokenUsage(
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_read_input_tokens=row.cache_read_tokens,
            cache_creation_input_tokens=row.cache_creation_tokens,
        ),
    )
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
        guardrail_report=(report := GuardrailReport.model_validate(row.guardrail_report_json)),
        guardrail_remedies=remedies_for(v.rule for v in report.violations),
        jd_extract=JDExtract.model_validate(row.jd_extract_json),
        llm_calls=row.llm_calls,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cache_read_tokens=row.cache_read_tokens,
        cache_creation_tokens=row.cache_creation_tokens,
        llm_model=row.llm_model,
        cost_usd=float(cost) if cost is not None else None,
        parent_package_id=row.parent_package_id,
        has_docx=row.docx_path is not None,
        has_pdf=row.pdf_path is not None,
        created_at=row.created_at,
        mode="tune" if row.mode == "tune" else "blocks",
        edits=[Edit.model_validate(e) for e in row.edits_json or []],
        source_document=(
            SourceDocument.model_validate(row.source_document_json)
            if row.source_document_json is not None
            else None
        ),
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


def error_violations(report_json: dict[str, Any] | None) -> int:
    """Error-severity violations in a stored report, read straight off the JSONB.

    Tolerant of a malformed or absent report rather than raising: this runs on every row of a list
    view, and one unparseable historical report must not 500 the whole Resumes queue. `GuardrailReport`
    validation stays where it belongs, on the single-package path.
    """
    violations = (report_json or {}).get("violations") or []
    if not isinstance(violations, list):
        return 0
    return sum(1 for v in violations if isinstance(v, dict) and v.get("severity") == "error")


async def _get_package(session: AsyncSession, user_id: uuid.UUID, package_id: uuid.UUID) -> Package:
    row = await repo.get_package(session, user_id, package_id)
    if row is None:
        raise not_found("package", package_id)
    return row


async def _basename(session: AsyncSession, user_id: uuid.UUID) -> str:
    answers = await profile_repo.get_answers(session, user_id)
    return download_basename(answers.get("name"))


@router.get("/packages", response_model=list[PackageListItem])
async def list_all_packages(
    user_id: UserDep,
    session: SessionDep,
    status: Literal["draft", "ready", "blocked"] | None = Query(default=None),
    applied: bool | None = Query(default=None),
    archived: bool = Query(default=False),
) -> list[PackageListItem]:
    rows = await repo.list_packages(
        session, user_id, status=status, applied=applied, archived=archived
    )
    return [
        PackageListItem(
            id=p.id,
            job_id=j.id,
            company=j.company,
            title=j.title,
            version=p.version,
            status=p.status,
            mode="tune" if p.mode == "tune" else "blocks",
            application_status=a.status if a else None,
            best_fit=j.best_fit,
            best_track_id=j.best_track_id,
            created_at=p.created_at,
            archived_at=p.archived_at,
            violations=error_violations(p.guardrail_report_json),
        )
        for p, j, a in rows
    ]


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


@router.post("/packages/{package_id}/archive", response_model=PackageOut)
async def archive_package(
    package_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> PackageOut:
    """ "Skip": the draft leaves the review queue and its job leaves the Jobs grid together.

    Archiving only the package would leave the job in recommendations, where Tailor would offer
    to write the very draft the user just skipped.
    """
    row = await _get_package(session, user_id, package_id)
    repo.set_archived(row, True)
    job = await job_repo.get_job(session, user_id, row.job_id)
    if job is None:
        raise not_found("job", row.job_id)
    job_repo.set_hidden(job, True)
    await session.commit()
    await session.refresh(row)
    return package_to_out(row)


class EditedVersion(NamedTuple):
    """What a human edit produces: the fields that change on the new version, plus its DOCX."""

    update: dict[str, Any]
    docx: bytes
    report: GuardrailReport


async def _edited_blocks_version(
    parent: Package, profile: Profile, extract: JDExtract, resume: ResumeDocument
) -> EditedVersion:
    """Re-validate the hand-edited resume against the parent's stored selection and re-render."""
    report = run_guardrails(
        resume, profile, parent.selection_block_ids, extract, cover_note=parent.cover_note
    )
    try:
        # python-docx builds a zip in memory; keep it off the event loop with the rest of the IO.
        base = profile.base_for(profile.get_track(parent.track_id))
        docx = await asyncio.to_thread(render_docx, resume, profile.block_map(), base.style)
    except OrphanBulletError:
        docx = b""
    return EditedVersion({"resume": resume}, docx, report)


async def _edited_tune_version(
    session: AsyncSession,
    storage: PackageStorage,
    user_id: uuid.UUID,
    parent: Package,
    profile: Profile,
    extract: JDExtract,
    patches: list[EditPatch],
) -> EditedVersion:
    """Rebuild the edit set against the stored document, re-validate it, and rewrite the DOCX.

    `before` always comes from the document, never from the request: the same rule the LLM is
    held to, so a client cannot smuggle in a paragraph the document never contained. An edit
    naming a paragraph that is not in the document keeps an empty `before` and is reported by
    the `tune-scope` guardrail rather than raising.
    """
    source = await load_source(session, storage, user_id)
    if source is None:
        raise HTTPException(
            status_code=422,
            detail="the resume document this package was tuned from is no longer stored; upload it again",
        )
    document, data = source
    if parent.source_document_json is not None and [
        p.model_dump() for p in document.paragraphs
    ] != [
        p.model_dump()
        for p in SourceDocument.model_validate(parent.source_document_json).paragraphs
    ]:
        # The upload was replaced since this package was tuned: paragraph ids no longer mean
        # the same lines, so an edit would silently land on the wrong text. Tailor again instead.
        raise HTTPException(
            status_code=422,
            detail="the resume document was replaced after this package was tuned; tailor the job again",
        )
    originals = {paragraph.id: paragraph.text for paragraph in document.paragraphs}
    edits = [
        Edit(
            paragraph_id=patch.paragraph_id,
            before=originals.get(patch.paragraph_id, ""),
            after=patch.after.strip(),
            reason="edited by user",
        )
        for patch in patches
    ]
    report = run_tune_guardrails(
        document, edits, extract, profile.guardrails, cover_note=parent.cover_note
    )
    # Same rule as the pipeline: the writer edits the user's own file, so a failing report
    # means nothing is written back and the human reads the violations instead.
    docx = b""
    if report.passed:
        try:
            docx = await asyncio.to_thread(render_tuned_docx, data, edits)
        except EngineError:
            docx = b""
    resume = to_resume_document(apply_edits(document, edits), build_header(profile.answers))
    return EditedVersion(
        {"resume": resume, "edits": edits, "source_document": document}, docx, report
    )


async def _mark_status(
    session: AsyncSession,
    user_id: uuid.UUID,
    parent: Package,
    status: str,
    response: Response,
) -> PackageOut:
    """Promote a draft to ready (or back). In place, no new version, nothing else touched."""
    if status == "ready":
        # Read the raw report rather than the strict `GuardrailReport` model: only `passed` and
        # the violation count matter here, and a report written before this field existed (or
        # patched in directly, as tests do) may be missing `rules_run`.
        report_json = parent.guardrail_report_json or {}
        passed = bool(report_json.get("passed"))
        violation_count = len(report_json.get("violations") or [])
        if parent.status == "blocked" or not passed:
            # The last gate before a human sends this to an employer. Naming the count is what
            # makes the 409 actionable: the Review page lists the violations themselves.
            raise HTTPException(
                status_code=409,
                detail=(
                    f"this package is blocked by {violation_count} guardrail violation(s); "
                    "fix them and regenerate before marking it ready"
                ),
            )
        latest = await job_repo.latest_package(session, user_id, parent.job_id)
        if latest is not None and latest.id != parent.id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"version {parent.version} is not the latest for this job "
                    f"(v{latest.version} is); mark that one ready instead"
                ),
            )
    repo.set_status(parent, status)
    await session.commit()
    await session.refresh(parent)
    response.status_code = 200
    return package_to_out(parent)


@router.patch(
    "/packages/{package_id}",
    response_model=PackageOut,
    status_code=201,
    responses={
        200: {"description": "The package's status was changed in place", "model": PackageOut},
        201: {
            "description": "A new package version was created",
            "headers": {
                "Location": {
                    "description": "URL of the newly created package version",
                    "schema": {"type": "string", "format": "uri"},
                }
            },
        },
        409: {
            "description": "Blocked by guardrails, or not the latest version",
            "content": {"application/problem+json": {}},
        },
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
    """Human edit -> re-validate -> re-render -> new version. Never bypasses guardrails.

    Blocks-mode packages are patched with `resume` and re-run through `run_guardrails` with the
    parent's stored selection; tune-mode packages are patched with `edits` and re-run through
    `run_tune_guardrails` against the uploaded document. The body must match the parent's mode:
    a resume has no meaning for a tuned document, and vice versa.
    """
    parent = await _get_package(session, user_id, package_id)
    if body.status is not None:
        return await _mark_status(session, user_id, parent, body.status, response)
    job = await job_repo.get_job(session, user_id, parent.job_id)
    if job is None:
        raise not_found("job", parent.job_id)
    profile = await load_profile_from_db(session, user_id)
    extract = JDExtract.model_validate(parent.jd_extract_json)
    tune = parent.mode == "tune"
    if body.edits is not None:
        if not tune:
            raise HTTPException(
                status_code=422,
                detail="this package was written from your block library; patch it with `resume`",
            )
        version = await _edited_tune_version(
            session, storage, user_id, parent, profile, extract, body.edits
        )
    else:
        if tune:
            raise HTTPException(
                status_code=422,
                detail="this package is a tune of your uploaded document; patch it with `edits`",
            )
        assert body.resume is not None  # the schema guarantees exactly one of the two
        version = await _edited_blocks_version(parent, profile, extract, body.resume)
    report, docx = version.report, version.docx

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
            **version.update,
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
    filename = f"{await _basename(session, user_id)}_Package.zip"
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
    ext = "docx" if name == "resume.docx" else "pdf"
    media = DOCX_MEDIA if name == "resume.docx" else PDF_MEDIA
    report = GuardrailReport.model_validate(row.guardrail_report_json)
    stem = await _basename(session, user_id)
    return FileResponse(
        path,
        media_type=media,
        filename=f"{stem}_Resume.{ext}",
        headers={GUARDRAIL_HEADER: "passed" if report.passed else "blocked"},
    )
