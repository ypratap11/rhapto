"""Tune-mode guardrails: scope, no new numbers, no invented entities, date consistency."""

from pathlib import Path

from helpers import demo_extract
from helpers_docx import build_fixture_docx

from rhapto.engine.document import parse_docx
from rhapto.engine.guardrails.tune import run_tune_guardrails
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.source_document import Edit, SourceDocument
from rhapto.profile.loader import load_profile


def _doc() -> SourceDocument:
    return parse_docx(build_fixture_docx(), "resume.docx")


def _bullet(doc: SourceDocument):  # type: ignore[no-untyped-def]
    return next(p for p in doc.paragraphs if p.role == "bullet")


def _rules(demo_profile_dir: Path) -> list[GuardrailRule]:
    return load_profile(demo_profile_dir).guardrails


def test_clean_edit_passes(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    report = run_tune_guardrails(
        doc,
        [
            Edit(
                paragraph_id=b.id,
                before=b.text,
                after="Led the Snowflake migration for 12 teams, reducing warehouse cost 30%.",
                reason="r",
            )
        ],
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note="I led a Snowflake migration.",
    )
    assert report.passed, report.violations
    assert report.rules_run[:2] == ["tune-scope", "no-new-numbers"]
    assert "no-invented-entities" in report.rules_run
    assert "date-consistency" in report.rules_run


def test_new_number_and_invented_entity_and_changed_year_are_caught(
    demo_profile_dir: Path,
) -> None:
    doc = _doc()
    b = _bullet(doc)
    title = next(p for p in doc.paragraphs if p.role == "entry_title")
    edits = [
        Edit(
            paragraph_id=b.id,
            before=b.text,
            after="Led the migration for 40 teams, saving $2M.",
            reason="r",
        ),
        Edit(
            paragraph_id=b.id,
            before=b.text,
            after="Led the Databricks rollout at Globex Corp.",
            reason="r",
        ),
        Edit(
            paragraph_id=title.id,
            before=title.text,
            after="Senior Data Program Manager\t2017 – 2025",
            reason="r",
        ),
    ]
    report = run_tune_guardrails(
        doc, edits, demo_extract(), _rules(demo_profile_dir), cover_note="We doubled revenue."
    )
    rules_hit = {v.rule for v in report.violations}
    assert not report.passed
    assert {"no-new-numbers", "no-invented-entities", "tune-scope"} <= rules_hit
    assert any(v.path == "cover_note" and v.rule == "no-new-numbers" for v in report.violations)
    assert any(v.path == "edits[2]" and v.rule == "tune-scope" for v in report.violations)
    assert any(v.path == "edits[2]" and v.rule == "date-consistency" for v in report.violations)
    assert all(v.severity == "error" for v in report.violations)
    numbers = next(v for v in report.violations if v.rule == "no-new-numbers")
    assert numbers.block_id == b.id


def test_scope_limits_bullet_edits(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    edits = [
        Edit(paragraph_id=b.id, before=b.text, after=f"Bullet variant {i}", reason="r")
        for i in range(7)
    ]
    report = run_tune_guardrails(
        doc, edits, demo_extract(), _rules(demo_profile_dir), cover_note=None
    )
    assert any(v.rule == "tune-scope" and "6" in v.message for v in report.violations)


def test_scope_flags_unknown_id_and_empty_after(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    edits = [
        Edit(paragraph_id="p999", before="", after="Something new.", reason="r"),
        Edit(paragraph_id=b.id, before=b.text, after="   ", reason="r"),
    ]
    report = run_tune_guardrails(
        doc, edits, demo_extract(), _rules(demo_profile_dir), cover_note=None
    )
    scope = [v for v in report.violations if v.rule == "tune-scope"]
    assert {v.path for v in scope} == {"edits[0]", "edits[1]"}
    assert any("p999" in v.message for v in scope)
    assert any("empty" in v.message for v in scope)


def test_inactive_rules_are_not_run(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    edits = [
        Edit(
            paragraph_id=b.id,
            before=b.text,
            after="Led the Databricks rollout in 2014.",
            reason="r",
        )
    ]
    rules = [GuardrailRule(rule="no-invented-entities", active=False)]
    report = run_tune_guardrails(doc, edits, demo_extract(), rules, cover_note=None)
    assert report.rules_run == ["tune-scope", "no-new-numbers"]
    assert {v.rule for v in report.violations} == {"no-new-numbers"}  # 2014 is not in the document


def test_five_bullet_edits_are_within_scope(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    summary = next(p for p in doc.paragraphs if p.role == "summary")
    edits = [
        Edit(
            paragraph_id=b.id,
            before=b.text,
            after=f"Delivered the program cutover {w}.",
            reason="r",
        )
        for w in ("early", "on time", "with finance", "with engineering", "with no downtime")
    ]
    edits.append(
        Edit(
            paragraph_id=summary.id,
            before=summary.text,
            after="Senior Data Program Manager with 8 years leading analytics programs.",
            reason="r",
        )
    )
    report = run_tune_guardrails(
        doc, edits, demo_extract(), _rules(demo_profile_dir), cover_note=None
    )
    assert report.passed, report.violations
