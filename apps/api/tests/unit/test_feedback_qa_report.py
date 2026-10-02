"""QA adversarial cases for the owner report: hostile text must not break the Markdown structure or
the spreadsheet. Fictional testers and invented text only."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from rhapto.services.feedback import FeedbackRecord, QuickAnswers, render_csv, render_markdown

KEY = b"k" * 32


def _rec(
    answers: dict[str, Any], *, form: str = "quick", area: str | None = "review"
) -> FeedbackRecord:
    return FeedbackRecord(
        id=uuid.uuid4(),
        user_id=uuid.UUID(int=7),
        email="tester-q@example.com",
        created_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        form=form,
        page_area=area,
        schema_version=1,
        answers=answers,
        app_version="0.1.0",
        job_id=None,
        package_id=None,
    )


def _cells(records: list[FeedbackRecord]) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(render_csv(records, key=KEY, with_emails=False))))


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r"])
@pytest.mark.parametrize(
    "payload", ['HYPERLINK("http://x.example","a")', "cmd|' /C calc'!A0", "1+1"]
)
def test_every_formula_lead_is_defused_in_a_free_text_cell(lead: str, payload: str) -> None:
    (row,) = _cells([_rec({"kind": "bug", "text": lead + payload})])
    assert row["quick.text"].startswith("'" + lead)


def test_formula_lead_in_a_survey_text_field_is_defused_too() -> None:
    answers = {"overall": {"fix_first": "=1+1", "pay_why": "@SUM(A1)", "quote_ok": True}}
    (row,) = _cells([_rec(answers, form="survey", area=None)])
    assert row["overall.fix_first"].startswith("'=")
    assert row["overall.pay_why"].startswith("'@")


def test_unknown_schema_row_with_a_formula_lead_is_not_executable() -> None:
    base = _rec({"=cmd": "x"}, form="survey", area=None)
    rec99 = FeedbackRecord(
        id=base.id,
        user_id=base.user_id,
        email=base.email,
        created_at=base.created_at,
        form=base.form,
        page_area=None,
        schema_version=99,
        answers=base.answers,
        app_version=base.app_version,
        job_id=None,
        package_id=None,
    )
    (row,) = _cells([rec99])
    assert not row["raw_answers"].startswith(("=", "+", "-", "@"))


def test_csv_round_trips_quotes_commas_newlines_emoji_and_rtl() -> None:
    text = 'He said "no", then\nleft \U0001f600 ‮evil‬ שלום'
    (row,) = _cells([_rec({"kind": "idea", "text": text})])
    assert row["quick.text"] == text


def test_markdown_multiline_text_cannot_inject_headings_or_bullets() -> None:
    hostile = "ok\n## Fake section\n- fake bullet\n# Tester feedback"
    out = render_markdown([_rec({"kind": "bug", "text": hostile})], key=KEY)
    headings = [line for line in out.splitlines() if line.startswith("#")]
    assert "## Fake section" not in headings and headings.count("# Tester feedback") == 1
    assert not any(line.startswith("- fake") for line in out.splitlines())


def test_markdown_never_shows_the_email_by_default_even_for_hostile_text() -> None:
    out = render_markdown([_rec({"kind": "bug", "text": "x"})], key=KEY)
    assert "tester-q@example.com" not in out


def test_report_handles_a_survey_whose_sections_are_all_empty_dicts() -> None:
    answers: dict[str, Any] = {
        name: {} for name in ("session", "profile", "review", "overall", "downloads")
    }
    out = render_markdown([_rec(answers, form="survey", area=None)], key=KEY)
    assert out.startswith("# Tester feedback")
    render_csv([_rec(answers, form="survey", area=None)], key=KEY)


def test_quick_answers_model_accepts_exactly_the_documented_kinds() -> None:
    for kind in ("bug", "confusing", "idea", "worked_well"):
        QuickAnswers(kind=kind)
