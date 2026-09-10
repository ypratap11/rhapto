from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path
from typing import Literal

from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available

FileName = Literal["resume.docx", "resume.pdf"]

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


class PackageStorage:
    """Rendered package files under <root>/<package_id>/."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def dir_for(self, package_id: str) -> Path:
        if not SAFE_ID.match(package_id):
            raise ValueError(f"invalid package id {package_id!r}")
        return self.root / package_id

    def write_docx(self, package_id: str, data: bytes) -> Path:
        target = self.dir_for(package_id)
        target.mkdir(parents=True, exist_ok=True)
        path = target / "resume.docx"
        path.write_bytes(data)
        return path

    def render_pdf(self, package_id: str, soffice_binary: str) -> Path | None:
        docx = self.path_for(package_id, "resume.docx")
        if docx is None or not soffice_available(soffice_binary):
            return None
        try:
            return convert_docx_to_pdf(docx, self.dir_for(package_id), binary=soffice_binary)
        except PdfRenderError:
            return None

    def path_for(self, package_id: str, name: FileName) -> Path | None:
        path = self.dir_for(package_id) / name
        return path if path.is_file() else None

    def read(self, package_id: str, name: FileName) -> bytes:
        path = self.path_for(package_id, name)
        if path is None:
            raise FileNotFoundError(f"{name} not found for package {package_id}")
        return path.read_bytes()

    def build_zip(
        self,
        package_id: str,
        cover_note: str,
        package_json: str,
        extra_files: dict[str, str] | None = None,
    ) -> bytes:
        """Zip the package files. `extra_files` maps archive name to text content (e.g. a
        guardrail-blocked notice) and is written last."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("resume.docx", "resume.pdf"):
                path = self.path_for(package_id, name)
                if path is not None:
                    zf.write(path, name)
            zf.writestr("cover-note.md", cover_note.rstrip("\n") + "\n")
            zf.writestr("package.json", package_json)
            for name, content in (extra_files or {}).items():
                zf.writestr(name, content)
        return buffer.getvalue()

    def delete(self, package_id: str) -> None:
        shutil.rmtree(self.dir_for(package_id), ignore_errors=True)
