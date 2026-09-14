from __future__ import annotations

import io
import logging
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session, get_storage
from rhapto.api.errors import not_found
from rhapto.api.schemas import ImportOut, ResumeDocumentOut
from rhapto.db.models import ResumeDocumentRow
from rhapto.db.repositories import documents as documents_repo
from rhapto.db.repositories import profile as repo
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry, WatchlistEntry
from rhapto.models.source_document import SourceDocument
from rhapto.profile.loader import dump_profile
from rhapto.services.documents import DocumentError, delete_resume_document, store_resume_document
from rhapto.services.enqueue import Enqueuer
from rhapto.services.profile_sync import (
    aggregator_row_to_model,
    base_row_to_model,
    block_row_to_model,
    guardrail_row_to_model,
    import_profile_dir,
    load_profile_from_db,
    track_row_to_model,
    watchlist_row_to_model,
)
from rhapto.services.storage import PackageStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile")
PROFILE_FILES = {
    "blocks.yaml",
    "tracks.yaml",
    "bases.yaml",
    "guardrails.yaml",
    "answers.yaml",
    "watchlist.yaml",
}

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]


def _location_keys(*answer_maps: dict[str, str]) -> set[str]:
    """The answers that feed `engine.scoring.location_preference_from_answers`, across both the
    old and the new map so a removed key still counts as a change."""
    return {
        key
        for answers in answer_maps
        for key in answers
        if key.startswith("location_") or key == "remote_ok"
    }


def _check_id(path_id: str, body_id: str) -> None:
    if path_id != body_id:
        raise HTTPException(
            status_code=422, detail=f"path id {path_id!r} does not match body id {body_id!r}"
        )


@router.get("/blocks", response_model=list[Block])
async def list_blocks(user_id: UserDep, session: SessionDep) -> list[Block]:
    return [block_row_to_model(r) for r in await repo.list_blocks(session, user_id)]


@router.put(
    "/blocks/{block_id}",
    response_model=Block,
    responses={
        200: {"description": "The block already existed and was replaced"},
        201: {"description": "The block was created", "model": Block},
    },
)
async def put_block(
    block_id: str,
    body: Block,
    response: Response,
    user_id: UserDep,
    session: SessionDep,
    enqueuer: EnqueuerDep,
) -> Block:
    _check_id(block_id, body.id)
    existed = await repo.get_block(session, user_id, block_id) is not None
    row = await repo.upsert_block(session, user_id, body)
    await session.commit()
    await enqueuer.enqueue("embed_blocks", user_id=str(user_id), block_ids=[block_id])
    response.status_code = 200 if existed else 201
    return block_row_to_model(row)


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(block_id: str, user_id: UserDep, session: SessionDep) -> Response:
    if not await repo.delete_block(session, user_id, block_id):
        raise not_found("block", block_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/bases", response_model=list[ResumeBase])
async def list_bases(user_id: UserDep, session: SessionDep) -> list[ResumeBase]:
    return [base_row_to_model(r) for r in await repo.list_bases(session, user_id)]


@router.put(
    "/bases/{base_id}",
    response_model=ResumeBase,
    responses={
        200: {"description": "The base already existed and was replaced"},
        201: {"description": "The base was created", "model": ResumeBase},
    },
)
async def put_base(
    base_id: str, body: ResumeBase, response: Response, user_id: UserDep, session: SessionDep
) -> ResumeBase:
    _check_id(base_id, body.id)
    existed = await repo.get_base(session, user_id, base_id) is not None
    row = await repo.upsert_base(session, user_id, body)
    await session.commit()
    response.status_code = 200 if existed else 201
    return base_row_to_model(row)


@router.delete("/bases/{base_id}", status_code=204)
async def delete_base(base_id: str, user_id: UserDep, session: SessionDep) -> Response:
    if not await repo.delete_base(session, user_id, base_id):
        raise not_found("base", base_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/tracks", response_model=list[Track])
async def list_tracks(user_id: UserDep, session: SessionDep) -> list[Track]:
    return [track_row_to_model(r) for r in await repo.list_tracks(session, user_id)]


@router.put(
    "/tracks/{track_id}",
    response_model=Track,
    responses={
        200: {"description": "The track already existed and was replaced"},
        201: {"description": "The track was created", "model": Track},
    },
)
async def put_track(
    track_id: str,
    body: Track,
    response: Response,
    user_id: UserDep,
    session: SessionDep,
    enqueuer: EnqueuerDep,
) -> Track:
    _check_id(track_id, body.id)
    existed = await repo.get_track(session, user_id, track_id) is not None
    row = await repo.upsert_track(session, user_id, body)
    await session.commit()
    try:
        await enqueuer.enqueue("rescore_jobs", user_id=str(user_id))
    except Exception:  # the row is committed; a queue outage must not fail the request
        logger.exception(
            "could not enqueue %s; the record is saved but not (re)scored", "score_jobs"
        )
    response.status_code = 200 if existed else 201
    return track_row_to_model(row)


@router.delete("/tracks/{track_id}", status_code=204)
async def delete_track(track_id: str, user_id: UserDep, session: SessionDep) -> Response:
    if not await repo.delete_track(session, user_id, track_id):
        raise not_found("track", track_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/guardrails", response_model=list[GuardrailRule])
async def list_guardrails(user_id: UserDep, session: SessionDep) -> list[GuardrailRule]:
    return [guardrail_row_to_model(r) for r in await repo.list_guardrails(session, user_id)]


@router.put(
    "/guardrails/{rule}",
    response_model=GuardrailRule,
    responses={
        200: {"description": "The guardrail rule already existed and was replaced"},
        201: {"description": "The guardrail rule was created", "model": GuardrailRule},
    },
)
async def put_guardrail(
    rule: str, body: GuardrailRule, response: Response, user_id: UserDep, session: SessionDep
) -> GuardrailRule:
    _check_id(rule, body.rule)
    existed = await repo.get_guardrail(session, user_id, rule) is not None
    row = await repo.upsert_guardrail(session, user_id, body)
    await session.commit()
    response.status_code = 200 if existed else 201
    return guardrail_row_to_model(row)


@router.delete("/guardrails/{rule}", status_code=204)
async def delete_guardrail(rule: str, user_id: UserDep, session: SessionDep) -> Response:
    if not await repo.delete_guardrail(session, user_id, rule):
        raise not_found("guardrail", rule)
    await session.commit()
    return Response(status_code=204)


@router.get("/answers", response_model=dict[str, str])
async def get_answers(user_id: UserDep, session: SessionDep) -> dict[str, str]:
    return await repo.get_answers(session, user_id)


@router.put("/answers", response_model=dict[str, str])
async def put_answers(
    body: dict[str, str], user_id: UserDep, session: SessionDep, enqueuer: EnqueuerDep
) -> dict[str, str]:
    previous = await repo.get_answers(session, user_id)
    await repo.set_answers(session, user_id, body)
    await session.commit()
    if any(previous.get(key) != body.get(key) for key in _location_keys(previous, body)):
        try:
            await enqueuer.enqueue("rescore_jobs", user_id=str(user_id))
        except Exception:  # the row is committed; a queue outage must not fail the request
            logger.exception(
                "could not enqueue %s; the record is saved but not (re)scored", "rescore_jobs"
            )
    return body


@router.get("/watchlist", response_model=list[WatchlistEntry])
async def get_watchlist(user_id: UserDep, session: SessionDep) -> list[WatchlistEntry]:
    return [watchlist_row_to_model(r) for r in await repo.list_watchlist(session, user_id)]


@router.put("/watchlist", response_model=list[WatchlistEntry])
async def put_watchlist(
    body: list[WatchlistEntry], user_id: UserDep, session: SessionDep
) -> list[WatchlistEntry]:
    await repo.replace_watchlist(session, user_id, body)
    await session.commit()
    return body


@router.get("/aggregators", response_model=list[AggregatorEntry])
async def get_aggregators(user_id: UserDep, session: SessionDep) -> list[AggregatorEntry]:
    return [aggregator_row_to_model(r) for r in await repo.list_aggregators(session, user_id)]


@router.put("/aggregators", response_model=list[AggregatorEntry])
async def put_aggregators(
    body: list[AggregatorEntry], user_id: UserDep, session: SessionDep
) -> list[AggregatorEntry]:
    await repo.replace_aggregators(session, user_id, body)
    await session.commit()
    return body


@router.post("/import", response_model=ImportOut)
async def import_profile(
    files: list[UploadFile],
    user_id: UserDep,
    session: SessionDep,
    enqueuer: EnqueuerDep,
) -> ImportOut:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        for upload in files:
            name = Path(upload.filename or "").name
            if name not in PROFILE_FILES:
                raise HTTPException(
                    status_code=422,
                    detail=f"unexpected file {name!r}; expected one of {sorted(PROFILE_FILES)}",
                )
            (target / name).write_bytes(await upload.read())
        profile = await import_profile_dir(session, user_id, target)
    await session.commit()
    await enqueuer.enqueue(
        "embed_blocks", user_id=str(user_id), block_ids=[b.id for b in profile.blocks]
    )
    try:
        await enqueuer.enqueue("rescore_jobs", user_id=str(user_id))
    except Exception:  # the row is committed; a queue outage must not fail the request
        logger.exception(
            "could not enqueue %s; the record is saved but not (re)scored", "score_jobs"
        )
    return ImportOut(
        blocks=len(profile.blocks),
        tracks=len(profile.tracks),
        bases=len(profile.bases),
        guardrails=len(profile.guardrails),
    )


@router.get("/export")
async def export_profile(user_id: UserDep, session: SessionDep) -> StreamingResponse:
    profile = await load_profile_from_db(session, user_id)
    with tempfile.TemporaryDirectory() as tmp:
        dump_profile(profile, Path(tmp))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(Path(tmp).glob("*.yaml")):
                zf.write(path, path.name)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="profile.zip"'},
    )


# --- the resume document tune mode rewrites ----------------------------------------------------


def document_out(row: ResumeDocumentRow) -> ResumeDocumentOut:
    return ResumeDocumentOut(
        filename=row.filename,
        uploaded_at=row.uploaded_at,
        document=SourceDocument.model_validate(row.parsed_json),
    )


@router.post("/resume-document", response_model=ResumeDocumentOut, status_code=201)
async def upload_resume_document(
    file: UploadFile,
    user_id: UserDep,
    session: SessionDep,
    storage: StorageDep,
) -> ResumeDocumentOut:
    """Accept one .docx, parse it, and keep it as the document tune mode rewrites.

    The bytes go to the storage volume, never into git and never into the package row; only
    the parsed paragraphs are stored in Postgres.
    """
    name = Path(file.filename or "").name
    try:
        row = await store_resume_document(session, storage, user_id, name, await file.read())
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return document_out(row)


@router.get("/resume-document", response_model=ResumeDocumentOut)
async def get_resume_document(user_id: UserDep, session: SessionDep) -> ResumeDocumentOut:
    row = await documents_repo.get_document(session, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no resume document uploaded")
    return document_out(row)


@router.delete("/resume-document", status_code=204)
async def delete_document(user_id: UserDep, session: SessionDep, storage: StorageDep) -> Response:
    """Idempotent: deleting nothing is still a 204, and tailoring falls back to blocks mode."""
    await delete_resume_document(session, storage, user_id)
    await session.commit()
    return Response(status_code=204)
