from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any

from docx import Document
from docx.shared import Pt

from rhapto.engine.guardrails.base import iter_bullets, iter_entries
from rhapto.engine.render.templates import template_for
from rhapto.engine.types import EngineError
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeDocument

FONT_NAME = "Calibri"
FONT_SIZE = Pt(11)


class OrphanBulletError(EngineError):
    """A bullet or entry cites a block that is not in the library. The renderer refuses to continue."""

    def __init__(self, path: str, block_id: str) -> None:
        super().__init__(f"{path} cites unknown block {block_id!r}")
        self.path = path
        self.block_id = block_id


def _check_provenance(resume: ResumeDocument, blocks: Mapping[str, Block]) -> None:
    for path, entry in iter_entries(resume):
        if entry.source_block_id not in blocks:
            raise OrphanBulletError(path, entry.source_block_id)
    for path, bullet in iter_bullets(resume):
        if bullet.source_block_id not in blocks:
            raise OrphanBulletError(path, bullet.source_block_id)


def render_docx(
    resume: ResumeDocument,
    blocks: Mapping[str, Block],
    style: Mapping[str, Any] | None = None,
) -> bytes:
    """Single column, standard headings, bullets via the built-in List Bullet style. No tables or images.

    Layout comes from `style["template"]` (see `render.templates`), defaulting to `classic` so a
    profile that asks for nothing renders as it always has. Provenance is checked before any
    layout runs: an orphan bullet is refused whichever template is selected.

    ResumeBase.section_order is not yet honoured - sections render in the order the composer
    returned them (stage 2).
    """
    _check_provenance(resume, blocks)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = FONT_SIZE
    template_for(style)(doc, resume)

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
