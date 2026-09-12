"""Tune-mode guardrails: scope, no new numbers, no invented entities, date consistency."""

from pathlib import Path

import pytest
from helpers import demo_extract
from helpers_docx import build_fixture_docx

from rhapto.engine.document import parse_docx
from rhapto.engine.guardrails.registry import UnknownGuardrailError
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


def test_unknown_rule_name_raises_but_blocks_only_rules_are_skipped(demo_profile_dir: Path) -> None:
    doc = _doc()
    b = _bullet(doc)
    clean = [Edit(paragraph_id=b.id, before=b.text, after="Ran the analytics roadmap.", reason="r")]
    blocks_only = [
        GuardrailRule(rule="no-unverified-metrics"),
        GuardrailRule(rule="attribution"),
        GuardrailRule(rule="visibility-context"),
        GuardrailRule(rule="provenance"),
    ]
    report = run_tune_guardrails(doc, clean, demo_extract(), blocks_only, cover_note=None)
    assert report.rules_run == ["tune-scope", "no-new-numbers"] and report.passed

    with pytest.raises(UnknownGuardrailError):
        run_tune_guardrails(
            doc, clean, demo_extract(), [GuardrailRule(rule="no-invented-entites")], cover_note=None
        )
    # Inactive typos are not validated, exactly as in `run_guardrails`.
    run_tune_guardrails(
        doc,
        clean,
        demo_extract(),
        [GuardrailRule(rule="no-invented-entites", active=False)],
        cover_note=None,
    )


def _after(doc: SourceDocument, text: str) -> list[Edit]:
    b = _bullet(doc)
    return [Edit(paragraph_id=b.id, before=b.text, after=text, reason="r")]


@pytest.mark.parametrize(
    ("after", "offending"),
    [
        # B1: the right half of an ASCII-hyphen range was never tokenised at all.
        ("Led the migration for 12 teams, cutting warehouse cost 30-85%.", "85%"),
        # B2: the document says "12 teams" and "8 years", not "$12M" and "8x".
        ("Led the migration for 12 teams, saving $12M.", "$12M"),
        ("Led the migration, improving throughput 8x.", "8x"),
        ("Led the migration, saving $555K for the platform team.", "$555K"),
        # The document's 12 is a team count, not a percentage.
        ("Led the Snowflake migration, cutting warehouse cost 12%.", "12%"),
    ],
)
def test_unit_aware_numbers_are_caught(demo_profile_dir: Path, after: str, offending: str) -> None:
    doc = _doc()
    report = run_tune_guardrails(
        doc, _after(doc, after), demo_extract(), _rules(demo_profile_dir), cover_note=None
    )
    numbers = [v for v in report.violations if v.rule == "no-new-numbers"]
    assert numbers, report.violations
    assert offending in numbers[0].message


@pytest.mark.parametrize(
    "after",
    [
        "Led the Snowflake migration for 12 teams, cutting warehouse cost 30%.",
        "Led the Snowflake migration for 12 teams, cutting warehouse cost 30 percent.",
        "Senior Data Program Manager with 8 years of delivery.",
    ],
)
def test_numbers_already_in_the_document_are_allowed(demo_profile_dir: Path, after: str) -> None:
    doc = _doc()
    report = run_tune_guardrails(
        doc, _after(doc, after), demo_extract(), _rules(demo_profile_dir), cover_note=None
    )
    assert report.passed, report.violations


def test_the_contact_line_is_not_a_pool_of_spare_numbers(demo_profile_dir: Path) -> None:
    """ "555 0100" is a phone number; a rewrite must not spend it on a metric."""
    doc = _doc()
    report = run_tune_guardrails(
        doc,
        _after(doc, "Led the migration for 555 teams."),
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note=None,
    )
    assert not report.passed
    assert any(v.rule == "no-new-numbers" and "555" in v.message for v in report.violations)


def test_cover_note_numbers_are_unit_aware_too(demo_profile_dir: Path) -> None:
    doc = _doc()
    report = run_tune_guardrails(
        doc, [], demo_extract(), _rules(demo_profile_dir), cover_note="I saved the team $12M."
    )
    assert any(
        v.path == "cover_note" and "$12M" in v.message and v.rule == "no-new-numbers"
        for v in report.violations
    )


def test_ordinary_capitalised_prose_does_not_trip_the_entity_rule(demo_profile_dir: Path) -> None:
    doc = _doc()
    report = run_tune_guardrails(
        doc,
        _after(doc, "Partnered with Finance and Legal on the Agile delivery of the roadmap."),
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note=None,
    )
    assert report.passed, report.violations


def test_an_invented_org_at_a_sentence_start_is_still_caught(demo_profile_dir: Path) -> None:
    doc = _doc()
    report = run_tune_guardrails(
        doc,
        _after(doc, "Globex Corp led the program with me."),
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note=None,
    )
    entities = [v for v in report.violations if v.rule == "no-invented-entities"]
    assert entities and "Globex Corp" in entities[0].message


def test_entity_containment_is_word_boundary(demo_profile_dir: Path) -> None:
    doc = _doc()
    # "Acme Analytics" is in the document; "Acme Analytica" is a different company.
    report = run_tune_guardrails(
        doc,
        _after(doc, "Ran the roadmap with Acme Analytica and the platform team."),
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note=None,
    )
    assert any(
        v.rule == "no-invented-entities" and "Acme Analytica" in v.message
        for v in report.violations
    )
    clean = run_tune_guardrails(
        doc,
        _after(doc, "Ran the roadmap with Acme Analytics and the platform team."),
        demo_extract(),
        _rules(demo_profile_dir),
        cover_note=None,
    )
    assert clean.passed, clean.violations


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


def test_period_codes_are_not_entities() -> None:
    from rhapto.engine.guardrails.tune import capitalised_runs

    assert capitalised_runs("Delivered Q3 results ahead of schedule.") == []
    assert capitalised_runs("Reduced FY24 operating costs by 12% across H1.") == []
    assert capitalised_runs("Reduced costs with Globex Corp in Q3.") == ["Globex Corp"]


def test_recombined_document_words_are_not_invented_entities(demo_profile_dir: Path) -> None:
    """Title Case skill phrases built from the document's own words pass; a new word does not."""
    doc = _doc()
    skill = next(p for p in doc.paragraphs if p.role == "skill")
    rules = load_profile(demo_profile_dir).guardrails

    def edit(text: str) -> list[Edit]:
        return [Edit(paragraph_id=skill.id, before=skill.text, after=text, reason="r")]

    ok = run_tune_guardrails(
        doc,
        edit("Platforms:  Snowflake Migration  •  Analytics Roadmap  •  Warehouse Cost"),
        demo_extract(),
        rules,
        cover_note=None,
    )
    assert not [v for v in ok.violations if v.rule == "no-invented-entities"], ok.violations
    bad = run_tune_guardrails(
        doc,
        edit("Platforms:  Snowflake  •  Databricks Lakehouse"),
        demo_extract(),
        rules,
        cover_note=None,
    )
    assert [v.rule for v in bad.violations] == ["no-invented-entities"]


def test_present_as_a_verb_is_not_a_date(demo_profile_dir: Path) -> None:
    doc = _doc()
    rules = load_profile(demo_profile_dir).guardrails
    ok = run_tune_guardrails(
        doc,
        _after(doc, "Present migration results to finance and engineering stakeholders."),
        demo_extract(),
        rules,
        cover_note=None,
    )
    assert not [v for v in ok.violations if v.rule == "date-consistency"], ok.violations
    bad = run_tune_guardrails(
        doc,
        _after(doc, "Ran the analytics roadmap, 2019 – present."),
        demo_extract(),
        rules,
        cover_note=None,
    )
    assert [v.rule for v in bad.violations] == ["date-consistency"]
