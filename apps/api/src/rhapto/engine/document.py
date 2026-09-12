"""The user's own resume DOCX as a list of role-tagged paragraphs. Pure: bytes in, model out."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from rhapto.engine.guardrails.metrics import (
    find_numeric_tokens,
    find_spelled_quantities,
    normalize_number,
)
from rhapto.models.resume_document import (
    ResumeBullet,
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)
from rhapto.models.source_document import DocParagraph, DocSection, Edit, SourceDocument

EDITABLE_ROLES = frozenset({"summary", "competency", "skill", "bullet"})
YEAR_RANGE = re.compile(r"(?:19|20)\d{2}\s*[-–—]\s*(?:(?:19|20)\d{2}|present|current)", re.I)
LABEL_LINE = re.compile(r"^[A-Za-z][A-Za-z /&]{1,40}:\s+\S")
# A run of digits long enough to plausibly be a phone number (with optional separators),
# e.g. "555 0100" or "(303) 555-0100" -- deliberately loose since it is only consulted for
# paragraphs between the name and the first heading.
PHONE_RUN = re.compile(r"\d[\d\-.\s]{5,}\d")
SUMMARY_WORDS = ("summary", "profile", "objective")
COMPETENCY_WORDS = ("competenc", "expertise", "highlights")
SKILL_WORDS = ("skill", "technolog", "tools")
CREDENTIAL_WORDS = ("education", "certification", "credential")
EXPERIENCE_WORDS = ("experience", "employment", "career", "projects", "development")


@dataclass(frozen=True)
class RawParagraph:
    text: str
    style: str
    bold: bool
    all_caps: bool
    has_tab: bool
    has_numbering: bool
    centered: bool


def _raw(paragraph) -> RawParagraph:  # type: ignore[no-untyped-def]
    text = paragraph.text.strip()
    runs = [r for r in paragraph.runs if r.text.strip()]
    bold = bool(runs) and all(bool(r.font.bold) for r in runs)
    numbering = (
        paragraph._p.pPr is not None
        and paragraph._p.pPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr"
        )
        is not None
    )
    return RawParagraph(
        text=text,
        style=paragraph.style.name if paragraph.style is not None else "",
        bold=bold,
        all_caps=text.isupper() and any(ch.isalpha() for ch in text),
        has_tab="\t" in paragraph.text,
        has_numbering=numbering,
        centered=paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER,
    )


def _is_heading(raw: RawParagraph) -> bool:
    """A section heading: either bold+ALL-CAPS text, or a Word "Heading" paragraph style.

    Either way it must be short and free of tab stops (a bold, all-caps, tabbed line is an
    `entry_title`, not a heading).
    """
    if raw.has_tab or len(raw.text) > 60:
        return False
    if raw.bold and raw.all_caps:
        return True
    return raw.style.startswith("Heading")


def _section_kind(heading: str) -> str:
    h = heading.casefold()
    for words, kind in (
        (SUMMARY_WORDS, "summary"),
        (COMPETENCY_WORDS, "competency"),
        (SKILL_WORDS, "skill"),
        (CREDENTIAL_WORDS, "credential"),
        (EXPERIENCE_WORDS, "experience"),
    ):
        if any(w in h for w in words):
            return kind
    return "other"


def classify(raws: list[RawParagraph]) -> list[DocParagraph]:
    """Role per paragraph. Index-stable: paragraph i is always `p<i>`, empty ones included as `other`."""
    out: list[DocParagraph] = []
    heading: str | None = None
    kind = "other"
    seen_text = 0
    previous_role = "other"
    for i, raw in enumerate(raws):
        pid = f"p{i}"
        if not raw.text:
            out.append(DocParagraph(id=pid, text="", role="other", section=heading))
            continue
        if seen_text == 0:
            role = "name"
        elif _is_heading(raw):
            role = "heading"
            heading = raw.text
            kind = _section_kind(raw.text)
        elif heading is None and (
            raw.centered or "|" in raw.text or "@" in raw.text or PHONE_RUN.search(raw.text)
        ):
            # Any paragraph between the name and the first heading is part of the contact
            # block, not just the line right after the name (multi-line contact blocks are
            # common: address on one line, phone/email on the next).
            role = "contact"
        elif raw.has_numbering or raw.style.startswith("List"):
            role = "bullet"
        elif raw.bold and YEAR_RANGE.search(raw.text):
            # No tab required: Rhapto's own renderer (and many real templates) right-aligns
            # the date range with spaces or a tab stop that never becomes a literal "\t".
            # `_split_title` handles both the tab and no-tab cases.
            role = "entry_title"
        elif previous_role == "entry_title":
            role = "entry_org"
        elif kind == "summary":
            role = "summary"
        elif kind == "competency" and LABEL_LINE.match(raw.text):
            role = "competency"
        elif kind == "skill" and LABEL_LINE.match(raw.text):
            role = "skill"
        elif kind == "credential":
            role = "credential"
        else:
            role = "other"
        seen_text += 1
        previous_role = role
        out.append(DocParagraph(id=pid, text=raw.text, role=role, section=heading))
    return out


def parse_docx(data: bytes, filename: str) -> SourceDocument:
    document = Document(io.BytesIO(data))
    paragraphs = classify([_raw(p) for p in document.paragraphs])
    sections: list[DocSection] = []
    for p in paragraphs:
        if p.role == "heading":
            sections.append(DocSection(heading=p.text, paragraph_ids=[]))
        elif p.text and sections and p.section == sections[-1].heading:
            sections[-1].paragraph_ids.append(p.id)
    return SourceDocument(filename=filename, paragraphs=paragraphs, sections=sections)


def document_numbers(doc: SourceDocument) -> set[str]:
    text = " ".join(p.text for p in doc.paragraphs)
    numbers = {normalize_number(t) for t in find_numeric_tokens(text)}
    return numbers | {q.casefold() for q in find_spelled_quantities(text)}


def document_entities(doc: SourceDocument) -> str:
    return "\n".join(p.text for p in doc.paragraphs if p.text)


def apply_edits(doc: SourceDocument, edits: list[Edit]) -> SourceDocument:
    replacement = {e.paragraph_id: e.after for e in edits}
    return doc.model_copy(
        update={
            "paragraphs": [
                p.model_copy(update={"text": replacement[p.id]}) if p.id in replacement else p
                for p in doc.paragraphs
            ]
        }
    )


def _split_title(text: str) -> tuple[str, str | None]:
    if "\t" in text:
        left, _, right = text.partition("\t")
        return left.strip(), right.strip() or None
    match = YEAR_RANGE.search(text)
    if match:
        return text[: match.start()].strip(" -–—"), match.group(0)
    return text.strip(), None


def section_kind_for(doc: SourceDocument, paragraph: DocParagraph) -> str:
    """The `_section_kind` (summary/competency/skill/credential/experience/other) that
    `paragraph` falls under, recomputed from its `section` heading text.

    The schema has no field to carry the resolved kind on `DocParagraph` itself, and adding
    one would mean hand-editing the generated models -- not allowed (see
    `packages/schemas/source_document.json`) -- so it is cheaply recomputed here instead of
    stored. `doc` is accepted (rather than just the heading string) for API symmetry with
    callers that already have the whole document and so this can later look at `doc.sections`
    if the resolution needs to get smarter than a text match.
    """
    if paragraph.section is None:
        return "other"
    return _section_kind(paragraph.section)


def to_resume_document(doc: SourceDocument, header: ResumeHeader) -> ResumeDocument:
    """A ResumeDocument view of the paragraphs so downstream code (package JSON, UI) keeps working.

    Bulleted paragraphs (role `bullet`) are routed by the kind of section they fall under
    (via `section_kind_for`) rather than always landing in Experience: bullets under a
    competency/skill section become a Skills entry, bullets under a credential section become
    a Credentials entry, and everything else attaches to the currently open Experience entry
    (or synthesizes one titled from the section heading). Within a section, all of that
    section's bulleted lines are grouped into a single entry titled after the section heading
    -- one entry per heading, one bullet per paragraph -- rather than one entry per bullet.
    """
    summary = [
        ResumeBullet(text=p.text, source_block_id=p.id)
        for p in doc.paragraphs
        if p.role == "summary"
    ]
    experience: list[ResumeEntry] = []
    skills: list[ResumeEntry] = []
    credentials: list[ResumeEntry] = []
    skills_by_heading: dict[str, ResumeEntry] = {}
    credentials_by_heading: dict[str, ResumeEntry] = {}
    current: ResumeEntry | None = None
    for p in doc.paragraphs:
        if p.role == "entry_title":
            role, period = _split_title(p.text)
            current = ResumeEntry(role=role, period=period, bullets=[], source_block_id=p.id)
            experience.append(current)
        elif p.role == "entry_org" and current is not None:
            current.org = p.text
        elif p.role == "bullet":
            kind = section_kind_for(doc, p)
            if kind in ("competency", "skill"):
                heading = p.section or "Skills"
                skill_entry = skills_by_heading.get(heading)
                if skill_entry is None:
                    skill_entry = ResumeEntry(title=heading, bullets=[], source_block_id=p.id)
                    skills_by_heading[heading] = skill_entry
                    skills.append(skill_entry)
                skill_entry.bullets.append(ResumeBullet(text=p.text, source_block_id=p.id))
            elif kind == "credential":
                heading = p.section or "Credentials"
                credential_entry = credentials_by_heading.get(heading)
                if credential_entry is None:
                    credential_entry = ResumeEntry(title=heading, bullets=[], source_block_id=p.id)
                    credentials_by_heading[heading] = credential_entry
                    credentials.append(credential_entry)
                credential_entry.bullets.append(ResumeBullet(text=p.text, source_block_id=p.id))
            else:
                if current is None:
                    current = ResumeEntry(
                        title=p.section or "Experience", bullets=[], source_block_id=p.id
                    )
                    experience.append(current)
                current.bullets.append(ResumeBullet(text=p.text, source_block_id=p.id))
        elif p.role in ("competency", "skill"):
            label, _, body = p.text.partition(":")
            skills.append(
                ResumeEntry(
                    title=label.strip(),
                    bullets=[ResumeBullet(text=body.strip(), source_block_id=p.id)],
                    source_block_id=p.id,
                )
            )
        elif p.role == "credential":
            credentials.append(ResumeEntry(title=p.text, bullets=[], source_block_id=p.id))
    sections = []
    if experience:
        sections.append(ResumeSection(title="Experience", kind="experience", entries=experience))
    if skills:
        sections.append(ResumeSection(title="Skills", kind="skills", entries=skills))
    if credentials:
        sections.append(ResumeSection(title="Credentials", kind="credentials", entries=credentials))
    return ResumeDocument(header=header, summary=summary, sections=sections)
