from __future__ import annotations

from pathlib import Path

import pytest
from helpers_docx import build_fixture_docx
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.models.source_document import SourceDocument
from rhapto.services.documents import (
    MAX_BYTES,
    DocumentError,
    delete_resume_document,
    load_source,
    store_resume_document,
)
from rhapto.services.storage import PackageStorage


async def test_rejects_non_docx_name(session: AsyncSession, user: User, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path)
    with pytest.raises(DocumentError, match="docx"):
        await store_resume_document(session, storage, user.id, "resume.pdf", b"%PDF-1.7")
    assert await load_source(session, storage, user.id) is None


async def test_rejects_oversized_payload(session: AsyncSession, user: User, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path)
    with pytest.raises(DocumentError, match="5 MB"):
        await store_resume_document(
            session, storage, user.id, "resume.docx", b"x" * (MAX_BYTES + 1)
        )
    assert not storage.document_dir(user.id).exists()


async def test_rejects_unparsable_docx(session: AsyncSession, user: User, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path)
    with pytest.raises(DocumentError, match="could not read"):
        await store_resume_document(session, storage, user.id, "resume.docx", b"not a zip")


async def test_store_load_and_delete(session: AsyncSession, user: User, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path)
    data = build_fixture_docx()
    row = await store_resume_document(session, storage, user.id, "Maya_Chen_Resume.docx", data)
    await session.commit()

    path = storage.document_dir(user.id) / "source.docx"
    assert path.read_bytes() == data and row.path == str(path)
    assert row.filename == "Maya_Chen_Resume.docx" and row.uploaded_at is not None
    parsed = SourceDocument.model_validate(row.parsed_json)
    assert parsed.filename == "Maya_Chen_Resume.docx"
    assert any(p.role == "summary" for p in parsed.paragraphs) and parsed.sections

    loaded = await load_source(session, storage, user.id)
    assert loaded is not None
    document, raw = loaded
    assert document == parsed and raw == data

    assert await delete_resume_document(session, storage, user.id) is True
    await session.commit()
    assert await load_source(session, storage, user.id) is None
    assert not path.exists()
    assert await delete_resume_document(session, storage, user.id) is False


async def test_second_store_replaces_the_row(
    session: AsyncSession, user: User, tmp_path: Path
) -> None:
    storage = PackageStorage(tmp_path)
    data = build_fixture_docx()
    first = await store_resume_document(session, storage, user.id, "first.docx", data)
    await session.commit()
    second = await store_resume_document(session, storage, user.id, "second.docx", data)
    await session.commit()
    assert second.id == first.id and second.filename == "second.docx"
