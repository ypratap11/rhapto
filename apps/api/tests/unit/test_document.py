from helpers_docx import build_fixture_docx

from rhapto.engine.document import (
    EDITABLE_ROLES,
    apply_edits,
    document_entities,
    document_numbers,
    parse_docx,
    to_resume_document,
)
from rhapto.models.resume_document import ResumeHeader
from rhapto.models.source_document import Edit


def test_parse_assigns_roles_and_sections() -> None:
    doc = parse_docx(build_fixture_docx(), "resume.docx")
    roles = [(p.role, p.text[:22]) for p in doc.paragraphs]
    assert roles[0] == ("name", "MAYA CHEN")
    assert roles[1][0] == "contact"
    assert ("heading", "PROFESSIONAL SUMMARY") in roles
    assert [r for r, _ in roles].count("summary") == 1
    assert [r for r, _ in roles].count("competency") == 1
    assert [r for r, _ in roles].count("entry_title") == 1
    assert [r for r, _ in roles].count("entry_org") == 1
    assert [r for r, _ in roles].count("bullet") == 2
    assert [r for r, _ in roles].count("skill") == 1
    assert [r for r, _ in roles].count("credential") == 1
    by_id = {p.id: p for p in doc.paragraphs}
    assert all(p.id.startswith("p") for p in doc.paragraphs)
    assert [s.heading for s in doc.sections] == [
        "PROFESSIONAL SUMMARY",
        "CORE COMPETENCIES",
        "PROFESSIONAL EXPERIENCE",
        "TECHNICAL SKILLS",
        "EDUCATION",
    ]
    summary = next(p for p in doc.paragraphs if p.role == "summary")
    assert summary.section == "PROFESSIONAL SUMMARY" and summary.id in doc.sections[0].paragraph_ids
    assert by_id[summary.id].text.startswith("Senior Data Program Manager")


def test_document_numbers_and_entities() -> None:
    doc = parse_docx(build_fixture_docx(), "resume.docx")
    numbers = document_numbers(doc)
    assert {"8", "12", "30", "2019", "2025"} <= numbers
    assert "Snowflake" in document_entities(doc) and "Acme Analytics" in document_entities(doc)


def test_apply_edits_and_mapping() -> None:
    doc = parse_docx(build_fixture_docx(), "resume.docx")
    bullet = next(p for p in doc.paragraphs if p.role == "bullet")
    edited = apply_edits(
        doc,
        [
            Edit(
                paragraph_id=bullet.id,
                before=bullet.text,
                after="Led the Snowflake migration across 12 teams.",
                reason="tighter",
            )
        ],
    )
    assert (
        next(p for p in edited.paragraphs if p.id == bullet.id).text
        == "Led the Snowflake migration across 12 teams."
    )
    assert doc.paragraphs != edited.paragraphs  # original untouched
    resume = to_resume_document(edited, ResumeHeader(name="Maya Chen"))
    assert (
        resume.summary[0].source_block_id
        == next(p for p in doc.paragraphs if p.role == "summary").id
    )
    exp = next(s for s in resume.sections if s.kind == "experience")
    assert (
        exp.entries[0].role == "Senior Data Program Manager"
        and exp.entries[0].period == "2019 – 2025"
    )
    assert (
        exp.entries[0].org == "Acme Analytics  |  Denver, CO" and len(exp.entries[0].bullets) == 2
    )
    assert exp.entries[0].bullets[0].source_block_id == bullet.id
    skills = next(s for s in resume.sections if s.kind == "skills")
    assert skills.entries[0].title in ("Program Delivery", "Platforms")
    assert EDITABLE_ROLES == frozenset({"summary", "competency", "skill", "bullet"})
