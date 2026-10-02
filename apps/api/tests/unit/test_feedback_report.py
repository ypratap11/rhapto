"""Owner report renderers: hand-built records, no DB. Fictional testers and invented text."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from rhapto.services import feedback as fb
from rhapto.services.feedback import (
    FeedbackRecord,
    pseudonym,
    render_csv,
    render_markdown,
)

KEY = b"k" * 32
A = uuid.UUID(int=1)
B = uuid.UUID(int=2)


def rec(
    *,
    user: uuid.UUID = A,
    email: str = "tester-a@example.com",
    form: str = "survey",
    area: str | None = None,
    answers: dict[str, Any] | None = None,
    day: int = 2,
    version: int = 1,
    app_version: str = "0.1.0",
) -> FeedbackRecord:
    return FeedbackRecord(
        id=uuid.uuid4(),
        user_id=user,
        email=email,
        created_at=datetime(2026, 10, day, 12, 0, tzinfo=UTC),
        form=form,
        page_area=area,
        schema_version=version,
        answers=answers or {},
        app_version=app_version,
        job_id=None,
        package_id=None,
    )


def quick(
    text: str | None, *, kind: str = "bug", area: str = "review", **kw: Any
) -> FeedbackRecord:
    answers: dict[str, Any] = {"kind": kind}
    if text is not None:
        answers["text"] = text
    return rec(form="quick", area=area, answers=answers, **kw)


def md(records: list[FeedbackRecord], **kw: Any) -> str:
    return render_markdown(records, key=KEY, with_emails=kw.pop("with_emails", False))


def section(text: str, heading: str) -> str:
    """The body under `## heading`, up to the next `## `."""
    start = text.index(f"## {heading}")
    rest = text[start + 3 :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_empty_input() -> None:
    assert render_markdown([], key=KEY, with_emails=False) == "No feedback yet.\n"


def test_rating_count_mean_and_histogram() -> None:
    records = [
        rec(answers={"getting_started": {"ease": e}}, user=u)
        for e, u in [(2, A), (4, A), (4, B), (5, B)]
    ]
    body = section(md(records), "2. Getting started")
    assert "Ease of getting started: n=4, mean 3.8, 1:0 2:1 3:0 4:2 5:1" in body


def test_choice_counts_follow_option_order() -> None:
    records = [
        rec(answers={"overall": {"would_use": v, "quote_ok": False}}) for v in ("no", "yes", "yes")
    ]
    body = section(md(records), "7. Overall")
    assert "Would use it: yes: 2, maybe: 0, no: 1" in body


def test_sections_are_in_spec_order() -> None:
    text = md([rec(answers={"overall": {"would_use": "yes"}})])
    positions = [text.index(f"## {n}") for n in ("1. ", "2. ", "3. ", "4. ", "5. ", "6. ", "7. ")]
    assert positions == sorted(positions)
    assert text.index("## Other pages") > positions[-1]
    assert text.index("## Quotable (consented)") > text.index("## Other pages")


def test_quick_feedback_sits_under_its_section_and_other_under_other_pages() -> None:
    records = [
        quick("Review page froze.", area="review"),
        quick("Pipeline card overlaps.", area="pipeline"),
        quick("Odd footer.", area="other"),
        quick("Jobs list slow.", area="jobs"),
    ]
    text = md(records)
    assert "Review page froze." in section(text, "5. Reviewing a package")
    assert "Pipeline card overlaps." in section(text, "6. Downloads")
    assert "Jobs list slow." in section(text, "4. Finding jobs")
    assert "Odd footer." in section(text, "Other pages")
    assert "Odd footer." not in section(text, "5. Reviewing a package")
    assert "quick/bug on review" in text


def test_would_have_noticed_is_labelled_self_reported() -> None:
    text = md([rec(answers={"review": {"would_have_noticed": "yes"}})])
    assert "Would have noticed anyway (self-reported): yes: 1" in text


def test_quotable_contains_only_consented_overall_text() -> None:
    consented = rec(
        answers={
            "overall": {"fix_first": "Speed up search.", "pay_why": "Worth it.", "quote_ok": True}
        }
    )
    refused = rec(
        user=B,
        answers={
            "overall": {"fix_first": "PRIVATE-REFUSED", "pay_why": "PRIVATE-PAY", "quote_ok": False}
        },
    )
    text = md([consented, refused])
    quotable = section(text, "Quotable (consented)")
    assert "Speed up search." in quotable and "Worth it." in quotable
    assert "PRIVATE-REFUSED" not in quotable and "PRIVATE-PAY" not in quotable
    # The refused text is still part of the report, just never offered as a quote.
    assert "PRIVATE-REFUSED" in section(text, "7. Overall")


def test_quotable_ignores_other_consented_text_fields() -> None:
    r = rec(
        answers={
            "getting_started": {"stuck": "STUCK-TEXT"},
            "overall": {"fix_first": "x", "quote_ok": True},
        }
    )
    assert "STUCK-TEXT" not in section(md([r]), "Quotable (consented)")


def test_no_email_or_user_id_by_default_and_email_with_flag() -> None:
    records = [rec(answers={"getting_started": {"stuck": "Lost."}})]
    plain = md(records)
    assert "tester-a@example.com" not in plain
    assert str(A) not in plain
    assert pseudonym(A, KEY) in plain
    flagged = md(records, with_emails=True)
    assert "tester-a@example.com" in flagged


def test_pseudonym_is_stable_and_key_dependent() -> None:
    assert pseudonym(A, KEY) == pseudonym(A, KEY)
    assert pseudonym(A, KEY) != pseudonym(A, b"z" * 32)
    assert pseudonym(A, KEY) != pseudonym(B, KEY)
    assert pseudonym(A, KEY).startswith("T-") and len(pseudonym(A, KEY)) == 8


def test_collision_widens_every_pseudonym_to_eight(monkeypatch: pytest.MonkeyPatch) -> None:
    def forged(user_id: uuid.UUID, key: bytes, width: int = 6) -> str:
        return "T-aaaaaa" if width == 6 else f"T-{user_id.int:08x}"

    monkeypatch.setattr(fb, "pseudonym", forged)
    records = [
        rec(user=A, answers={"getting_started": {"stuck": "one"}}),
        rec(user=B, answers={"getting_started": {"stuck": "two"}}),
    ]
    text = md(records)
    assert "T-aaaaaa" not in text
    assert "T-00000001" in text and "T-00000002" in text


def test_no_collision_keeps_six() -> None:
    text = md([rec(answers={"getting_started": {"stuck": "one"}})])
    assert pseudonym(A, KEY, 6) in text and pseudonym(A, KEY, 8) not in text


def test_unknown_schema_version_is_printed_raw_without_crashing() -> None:
    odd = rec(version=99, answers={"mystery": {"x": 1}})
    good = rec(answers={"getting_started": {"ease": 5}})
    text = md([odd, good])
    unrecognised = section(text, "Unrecognised")
    assert "schema_version=99" in unrecognised and '"mystery"' in unrecognised
    assert "n=1, mean 5.0" in text  # the good row is still analysed


def test_header_counts_testers_dates_and_versions() -> None:
    records = [
        rec(user=A, day=2, app_version="0.1.0+aaa", answers={"overall": {"would_use": "yes"}}),
        quick("hi", user=B, day=5, app_version="0.1.0+bbb"),
    ]
    head = md(records).split("\n## ")[0]
    assert "2 responses (1 surveys, 1 quick) from 2 testers" in head
    assert "2026-10-02 to 2026-10-05" in head
    assert "0.1.0+aaa, 0.1.0+bbb" in head


# ---- CSV -------------------------------------------------------------------------------------


def parse(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_fixed_columns_and_values() -> None:
    survey = rec(
        answers={
            "getting_started": {"ease": 4, "stuck": "a, b\nc"},
            "overall": {"would_use": "yes", "quote_ok": True},
        }
    )
    q = quick("It broke", kind="idea", area="jobs")
    q.answers["rating"] = 3
    text = render_csv([survey, q], key=KEY, with_emails=False)
    header = text.splitlines()[0].split(",")
    assert header[:2] == ["id", "tester"]
    assert header[2:8] == ["created_at", "form", "page_area", "app_version", "job_id", "package_id"]
    assert header[-4:] == ["quick.kind", "quick.rating", "quick.text", "raw_answers"]
    assert "email" not in header
    first, second = parse(text)
    assert first["getting_started.stuck"] == "a, b\nc"  # csv quoting round-trips commas/newlines
    assert first["getting_started.ease"] == "4"
    assert first["overall.quote_ok"] == "true"
    assert first["form"] == "survey" and first["page_area"] == ""
    assert second["quick.kind"] == "idea" and second["quick.rating"] == "3"
    assert second["page_area"] == "jobs" and second["getting_started.ease"] == ""


def test_csv_column_order_is_stable_across_inputs() -> None:
    a = render_csv([rec(answers={"overall": {"would_use": "yes"}})], key=KEY, with_emails=False)
    b = render_csv([quick("x")], key=KEY, with_emails=False)
    assert a.splitlines()[0] == b.splitlines()[0]


def test_csv_email_only_with_flag() -> None:
    records = [quick("x")]
    assert "tester-a@example.com" not in render_csv(records, key=KEY, with_emails=False)
    flagged = render_csv(records, key=KEY, with_emails=True)
    assert parse(flagged)[0]["email"] == "tester-a@example.com"


@pytest.mark.parametrize("lead", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_formula_guard(lead: str) -> None:
    text = render_csv([quick(f"{lead}SUM(A1)")], key=KEY, with_emails=False)
    cell = parse(text)[0]["quick.text"]
    assert cell.startswith("'") and cell.endswith("SUM(A1)")


def test_csv_leaves_ordinary_text_alone() -> None:
    assert (
        parse(render_csv([quick("fine = ok")], key=KEY, with_emails=False))[0]["quick.text"]
        == "fine = ok"
    )


def test_csv_empty_is_header_only() -> None:
    text = render_csv([], key=KEY, with_emails=False)
    assert len(text.splitlines()) == 1


def test_csv_unknown_schema_row_does_not_crash() -> None:
    rows = parse(render_csv([rec(version=99, answers={"x": 1})], key=KEY, with_emails=False))
    assert rows[0]["form"] == "survey" and rows[0]["overall.would_use"] == ""
    assert rows[0]["raw_answers"] == '{"x": 1}'  # nothing stored is dropped from the export


def test_csv_raw_answers_is_blank_for_a_known_row() -> None:
    assert parse(render_csv([quick("x")], key=KEY, with_emails=False))[0]["raw_answers"] == ""
