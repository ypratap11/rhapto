from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any

from docx import Document
from docx.shared import Inches, Pt

from rhapto.engine.guardrails.base import iter_bullets, iter_entries
from rhapto.engine.types import EngineError
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeDocument

FONT_NAME = "Calibri"
FONT_SIZE = Pt(11)

# ATS-safe standard headings. The section title the LLM wrote is ignored; kind is a validated
# Literal, so the heading can never be a fabricated or non-standard label.
SECTION_HEADINGS = {
    "experience": "Experience",
    "projects": "Projects",
    "skills": "Skills",
    "credentials": "Credentials",
}


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


def _heading(doc: Any, text: str) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(text.upper())
    run.bold = True
    run.font.size = Pt(12)
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(2)


def render_docx(resume: ResumeDocument, blocks: Mapping[str, Block]) -> bytes:
    """Single column, standard headings, bullets via the built-in List Bullet style. No tables or images.

    Headings come from section.kind via SECTION_HEADINGS; ResumeSection.title is not rendered.
    ResumeBase.section_order is not yet honoured - sections render in the order the composer
    returned them (stage 2).
    """
    _check_provenance(resume, blocks)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = FONT_SIZE
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Inches(0.7)
        section.left_margin = section.right_margin = Inches(0.8)

    name = doc.add_paragraph()
    name_run = name.add_run(resume.header.name)
    name_run.bold = True
    name_run.font.size = Pt(16)
    header = resume.header
    contact = " | ".join(filter(None, [header.email, header.phone, header.location, *header.links]))
    if contact:
        doc.add_paragraph(contact)

    if resume.summary:
        _heading(doc, "Summary")
        doc.add_paragraph(" ".join(b.text for b in resume.summary))

    for resume_section in resume.sections:
        _heading(doc, SECTION_HEADINGS.get(resume_section.kind, resume_section.kind))
        for entry in resume_section.entries:
            head = " | ".join(filter(None, [entry.role or entry.title, entry.org, entry.period]))
            if head:
                paragraph = doc.add_paragraph()
                paragraph.add_run(head).bold = True
            for bullet in entry.bullets:
                doc.add_paragraph(bullet.text, style="List Bullet")

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
