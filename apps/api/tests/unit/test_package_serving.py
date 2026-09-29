"""No file leaves the server for a package whose guardrail report failed (plan-review-2, I-1).

Phase 5 stops NEW blocked packages from writing a DOCX. Rows stored before it were rendered "for
review" and still have the file on disk, so the serving paths refuse independently of the writer.
`package_file` is called directly with its two lookups stubbed, so this runs without Postgres;
the same behaviour over HTTP is `test_blocked_package_download_is_unmistakable` (CI).
"""

import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from rhapto.api.routers import packages as router
from rhapto.services.storage import PackageStorage

BLOCKED = {"passed": False, "rules_run": ["completeness"], "violations": []}
PASSED = {"passed": True, "rules_run": ["completeness"], "violations": []}


def _stub_lookups(monkeypatch: pytest.MonkeyPatch, report: dict[str, Any]) -> None:
    async def get_package(session: object, user_id: object, package_id: uuid.UUID) -> Any:
        return SimpleNamespace(id=package_id, guardrail_report_json=report)

    async def basename(session: object, user_id: object) -> str:
        return "Maya_Chen"

    monkeypatch.setattr(router, "_get_package", get_package)
    monkeypatch.setattr(router, "_basename", basename)


def _store_with_files(tmp_path: Path, package_id: uuid.UUID) -> PackageStorage:
    store = PackageStorage(tmp_path)
    store.write_docx(str(package_id), b"PK legacy docx")
    (store.dir_for(str(package_id)) / "resume.pdf").write_bytes(b"%PDF legacy")
    return store


@pytest.mark.parametrize("name", ["resume.docx", "resume.pdf"])
async def test_a_blocked_package_with_a_file_on_disk_is_not_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """The known-bad input: the file IS there, exactly as it is for a pre-Phase-5 blocked row."""
    package_id = uuid.uuid4()
    store = _store_with_files(tmp_path, package_id)
    assert store.path_for(str(package_id), name) is not None
    _stub_lookups(monkeypatch, BLOCKED)
    with pytest.raises(HTTPException) as caught:
        await router.package_file(package_id, name, uuid.uuid4(), None, store)  # type: ignore[arg-type]
    assert caught.value.status_code == 409 and "guardrails" in str(caught.value.detail)


async def test_a_passed_package_is_still_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_id = uuid.uuid4()
    store = _store_with_files(tmp_path, package_id)
    _stub_lookups(monkeypatch, PASSED)
    response = await router.package_file(
        package_id,
        "resume.docx",
        uuid.uuid4(),
        None,
        store,  # type: ignore[arg-type]
    )
    assert isinstance(response, FileResponse)


async def test_a_blocked_package_with_no_file_is_still_a_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing was rendered (every blocked package since Phase 5): 404, as before, not 409."""
    _stub_lookups(monkeypatch, BLOCKED)
    with pytest.raises(HTTPException) as caught:
        await router.package_file(
            uuid.uuid4(),
            "resume.docx",
            uuid.uuid4(),
            None,
            PackageStorage(tmp_path),  # type: ignore[arg-type]
        )
    assert caught.value.status_code == 404


def test_the_zip_leaves_the_documents_out_when_asked_even_if_they_are_on_disk(
    tmp_path: Path,
) -> None:
    package_id = uuid.uuid4()
    store = _store_with_files(tmp_path, package_id)
    withheld = store.build_zip(
        str(package_id), "note", "{}", {"GUARDRAILS-BLOCKED.md": "x"}, include_documents=False
    )
    with zipfile.ZipFile(__import__("io").BytesIO(withheld)) as zf:
        assert sorted(zf.namelist()) == ["GUARDRAILS-BLOCKED.md", "cover-note.md", "package.json"]
    included = store.build_zip(str(package_id), "note", "{}")
    with zipfile.ZipFile(__import__("io").BytesIO(included)) as zf:
        assert {"resume.docx", "resume.pdf"} <= set(zf.namelist())
