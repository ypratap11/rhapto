import io
import zipfile
from pathlib import Path

import pytest

from rhapto.services import storage as storage_mod
from rhapto.services.storage import PackageStorage


def test_write_read_and_missing(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    path = store.write_docx("p1", b"PK-docx")
    assert path == tmp_path / "p1" / "resume.docx" and path.read_bytes() == b"PK-docx"
    assert store.read("p1", "resume.docx") == b"PK-docx"
    assert store.path_for("p1", "resume.pdf") is None
    assert store.path_for("p1", "resume.docx") == path


def test_render_pdf_skips_when_soffice_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: False)
    assert store.render_pdf("p1", "soffice") is None


def test_render_pdf_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: True)

    def fake_convert(
        docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180
    ) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(storage_mod, "convert_docx_to_pdf", fake_convert)
    assert store.render_pdf("p1", "soffice") == tmp_path / "p1" / "resume.pdf"


def test_render_pdf_swallows_render_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rhapto.engine.render.pdf import PdfRenderError

    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: True)

    def boom(*args: object, **kwargs: object) -> Path:
        raise PdfRenderError("LibreOffice failed")

    monkeypatch.setattr(storage_mod, "convert_docx_to_pdf", boom)
    assert store.render_pdf("p1", "soffice") is None


def test_zip_contains_files(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    data = store.build_zip("p1", "Dear team.", '{"version": 1}')
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert set(zf.namelist()) == {"resume.docx", "cover-note.md", "package.json"}
        assert zf.read("cover-note.md") == b"Dear team.\n"


def test_delete(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    store.delete("p1")
    assert not (tmp_path / "p1").exists()
    store.delete("p1")  # idempotent


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".", "..", "x\\y", "a b"])
def test_rejects_unsafe_package_ids(tmp_path: Path, bad: str) -> None:
    store = PackageStorage(tmp_path)
    with pytest.raises(ValueError, match="invalid package id"):
        store.dir_for(bad)


def test_accepts_uuid_package_ids(tmp_path: Path) -> None:
    import uuid

    store = PackageStorage(tmp_path)
    pid = str(uuid.uuid4())
    assert store.dir_for(pid) == tmp_path / pid
