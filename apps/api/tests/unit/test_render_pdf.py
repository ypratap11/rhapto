import subprocess
from pathlib import Path
from typing import Any

import pytest

from rhapto.engine.render import pdf


def test_soffice_available_uses_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pdf.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None
    )
    assert pdf.soffice_available() is True
    assert pdf.soffice_available("nope") is False


def test_convert_runs_headless_and_returns_pdf_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    seen: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen["cmd"] = cmd
        (out_dir / "resume.pdf").write_bytes(b"%PDF")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(pdf.subprocess, "run", fake_run)
    result = pdf.convert_docx_to_pdf(docx_path, out_dir, binary="soffice")
    assert result == out_dir / "resume.pdf"
    assert seen["cmd"][:4] == ["soffice", "--headless", "--convert-to", "pdf"]
    assert str(docx_path) in seen["cmd"] and "--outdir" in seen["cmd"]


def test_convert_raises_when_no_pdf_produced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docx_path = tmp_path / "resume.docx"
    docx_path.write_bytes(b"fake")
    monkeypatch.setattr(
        pdf.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, b"", b"")
    )
    with pytest.raises(pdf.PdfRenderError, match="did not produce"):
        pdf.convert_docx_to_pdf(docx_path, tmp_path)


def test_convert_raises_when_binary_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(cmd: list[str], **kw: Any) -> None:
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(pdf.subprocess, "run", missing)
    with pytest.raises(pdf.PdfRenderError, match="not found"):
        pdf.convert_docx_to_pdf(tmp_path / "x.docx", tmp_path, binary="nope")


def test_convert_raises_on_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(cmd: list[str], **kw: Any) -> None:
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr=b"boom")

    monkeypatch.setattr(pdf.subprocess, "run", failing)
    with pytest.raises(pdf.PdfRenderError, match="LibreOffice failed"):
        pdf.convert_docx_to_pdf(tmp_path / "x.docx", tmp_path)


def test_convert_raises_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(cmd: list[str], **kw: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout", 180))

    monkeypatch.setattr(pdf.subprocess, "run", slow)
    with pytest.raises(pdf.PdfRenderError, match="LibreOffice failed"):
        pdf.convert_docx_to_pdf(tmp_path / "x.docx", tmp_path, timeout=1)
