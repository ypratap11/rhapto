from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rhapto.engine.types import EngineError


class PdfRenderError(EngineError):
    """LibreOffice is missing or did not produce a PDF."""


def soffice_available(binary: str = "soffice") -> bool:
    return shutil.which(binary) is not None


def convert_docx_to_pdf(
    docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180
) -> Path:
    """Convert the rendered DOCX with headless LibreOffice so DOCX and PDF never drift."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [binary, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise PdfRenderError(f"LibreOffice binary {binary!r} not found") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PdfRenderError(f"LibreOffice failed: {exc}") from exc
    pdf_path = out_dir / f"{docx_path.stem}.pdf"
    if not pdf_path.exists():
        raise PdfRenderError(f"LibreOffice did not produce {pdf_path}")
    return pdf_path
