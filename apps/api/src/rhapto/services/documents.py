"""Storing and loading the resume document tune mode rewrites.

The split is deliberate: the parsed `SourceDocument` lives in Postgres (small, queryable, and
what the engine reasons about) while the original bytes live on the storage volume (what the
writer edits in place). This module is the only place that keeps the two halves in step, so
the API and the worker cannot disagree about where the upload went.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import ResumeDocumentRow
from rhapto.db.repositories import documents as documents_repo
from rhapto.engine.document import parse_docx
from rhapto.models.source_document import SourceDocument
from rhapto.services.storage import PackageStorage

MAX_BYTES = 5 * 1024 * 1024
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentError(Exception):
    """Upload rejected: not a .docx, too large, or unreadable."""


async def store_resume_document(
    session: AsyncSession,
    storage: PackageStorage,
    user_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> ResumeDocumentRow:
    """Parse, store and index one upload, replacing whatever the user had before.

    Nothing is written to disk until the document parses, so a rejected upload leaves no
    orphan file behind.
    """
    if not filename.lower().endswith(".docx"):
        raise DocumentError("upload a .docx file")
    if len(data) > MAX_BYTES:
        raise DocumentError("the document must be 5 MB or smaller")
    try:
        parsed = await asyncio.to_thread(parse_docx, data, filename)
    except Exception as exc:  # python-docx raises several types for corrupt files
        raise DocumentError("could not read the document; is it a valid .docx?") from exc
    path = await asyncio.to_thread(storage.write_document, user_id, data)
    return await documents_repo.upsert_document(
        session, user_id, filename=filename, path=str(path), parsed=parsed.model_dump(mode="json")
    )


async def load_source(
    session: AsyncSession, storage: PackageStorage, user_id: uuid.UUID
) -> tuple[SourceDocument, bytes] | None:
    """Both halves of the stored document, or None if the user has not uploaded one.

    A row whose file has vanished from the volume counts as "no document": tune mode cannot
    run on half of it, and the honest fix is for the user to upload again.
    """
    row = await documents_repo.get_document(session, user_id)
    if row is None:
        return None
    try:
        data = await asyncio.to_thread(storage.read_document, user_id)
    except FileNotFoundError:
        return None
    return SourceDocument.model_validate(row.parsed_json), data


async def delete_resume_document(
    session: AsyncSession, storage: PackageStorage, user_id: uuid.UUID
) -> bool:
    """Drop the row and the file. False when there was nothing stored."""
    deleted = await documents_repo.delete_document(session, user_id)
    await asyncio.to_thread(storage.delete_document, user_id)
    return deleted
