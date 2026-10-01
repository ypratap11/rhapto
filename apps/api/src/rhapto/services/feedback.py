"""Tester feedback: the answer schemas (the only writer's contract) and, later, the owner report.

Pure module: imports pydantic and the standard library only, so the API router and the CLI share one
definition (`services-do-not-import-entrypoints` holds).

Free text is validated here, not left to Postgres: `jsonb` refuses U+0000 with a DataError that would
surface as a 500, and a 500 is the one path that logs. The validator's message never quotes the value.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION = 1
TEXT_MAX = 2000

FeedbackForm = Literal["survey", "quick"]
PageArea = Literal[
    "dashboard",
    "jobs",
    "job_detail",
    "review",
    "resumes",
    "pipeline",
    "profile",
    "settings",
    "other",
]
Rating = Annotated[int, Field(ge=1, le=5)]
YesNoUnsure = Literal["yes", "no", "not_sure"]

_ALLOWED_CONTROLS = frozenset("\n\t")


def _clean_text(value: str) -> str | None:
    """Reject NUL and C0 controls (except newline and tab); blank text becomes None."""
    # Also lone UTF-16 surrogates: json.loads accepts "\ud800", but jsonb refuses it (a 500).
    if any(
        (ord(ch) < 0x20 and ch not in _ALLOWED_CONTROLS) or 0xD800 <= ord(ch) <= 0xDFFF
        for ch in value
    ):
        # Deliberately generic: the value must never be echoed into an error body or a log.
        raise ValueError("text contains control characters")
    return value or None


FreeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=TEXT_MAX),
    AfterValidator(_clean_text),
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionSection(_Strict):  # section 1
    task: (
        Literal["find_jobs", "tailor_resume", "review_package", "set_up_profile", "other"] | None
    ) = None
    task_other: FreeText | None = None
    finished: Literal["yes", "partly", "no"] | None = None
    minutes: Literal["lt_10", "10_30", "30_60", "gt_60"] | None = None


class GettingStartedSection(_Strict):
    ease: Rating | None = None
    stuck: FreeText | None = None


class ProfileSection(_Strict):
    ease: Rating | None = None
    missing_or_confusing: FreeText | None = None


class FindingJobsSection(_Strict):
    match_quality: Rating | None = None
    bad_match_example: FreeText | None = None


class ReviewSection(_Strict):
    resume_quality: Rating | None = None
    flagged: YesNoUnsure | None = None
    flag_verdict: Literal["right", "false_alarm", "not_sure"] | None = None
    would_have_noticed: YesNoUnsure | None = None  # self-report; labelled as such in the report
    wrongly_blocked: FreeText | None = None


class DownloadsSection(_Strict):
    looked_right: Literal["yes", "no"] | None = None
    problems: FreeText | None = None


class OverallSection(_Strict):
    would_use: Literal["yes", "maybe", "no"] | None = None
    would_pay_19: Literal["yes", "maybe", "no"] | None = None
    pay_why: FreeText | None = None
    fix_first: FreeText | None = None
    quote_ok: bool = False  # spec: default no


class SurveyAnswers(_Strict):
    """Every section optional, so every section is skippable."""

    session: SessionSection | None = None
    getting_started: GettingStartedSection | None = None
    profile: ProfileSection | None = None
    finding_jobs: FindingJobsSection | None = None
    review: ReviewSection | None = None
    downloads: DownloadsSection | None = None
    overall: OverallSection | None = None


class QuickAnswers(_Strict):
    kind: Literal["bug", "confusing", "idea", "worked_well"]
    rating: Rating | None = None
    text: FreeText | None = None


# Which quick-feedback areas the report prints under which survey section. `other` maps to no
# section ("Other pages").
SECTION_AREAS: dict[str, tuple[PageArea, ...]] = {
    "getting_started": ("settings",),
    "profile": ("profile",),
    "finding_jobs": ("dashboard", "jobs", "job_detail"),
    "review": ("review",),
    "downloads": ("resumes", "pipeline"),
}


# ---- Owner report ---------------------------------------------------------------------------
# Pure functions over plain records, so they are testable without Typer or a database. Output is for
# the maintainer's terminal only; nothing here is reachable over HTTP.


@dataclass(frozen=True)
class FeedbackRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    created_at: datetime
    form: str
    page_area: str | None
    schema_version: int
    answers: dict[str, Any]
    app_version: str
    job_id: uuid.UUID | None
    package_id: uuid.UUID | None


PSEUDONYM_SALT = b"rhapto-feedback-pseudonym-v1"

_Field = tuple[
    str, str, str, tuple[str, ...]
]  # (name, kind rating|choice|text|flag, label, options); flag = CSV only

# The report's order is the spec's section order.
_SURVEY_SECTIONS: tuple[tuple[str, str, tuple[_Field, ...]], ...] = (
    (
        "session",
        "1. The session",
        (
            (
                "task",
                "choice",
                "What they tried to do",
                ("find_jobs", "tailor_resume", "review_package", "set_up_profile", "other"),
            ),
            ("task_other", "text", "What they tried (other)", ()),
            ("finished", "choice", "Finished it", ("yes", "partly", "no")),
            ("minutes", "choice", "Minutes", ("lt_10", "10_30", "30_60", "gt_60")),
        ),
    ),
    (
        "getting_started",
        "2. Getting started",
        (
            ("ease", "rating", "Ease of getting started", ()),
            ("stuck", "text", "Where they got stuck", ()),
        ),
    ),
    (
        "profile",
        "3. Profile",
        (
            ("ease", "rating", "Ease of setting up the profile", ()),
            ("missing_or_confusing", "text", "Missing or confusing", ()),
        ),
    ),
    (
        "finding_jobs",
        "4. Finding jobs",
        (
            ("match_quality", "rating", "Match quality", ()),
            ("bad_match_example", "text", "A bad match", ()),
        ),
    ),
    (
        "review",
        "5. Reviewing a package",
        (
            ("resume_quality", "rating", "Resume quality", ()),
            ("flagged", "choice", "A guardrail flagged something", ("yes", "no", "not_sure")),
            ("flag_verdict", "choice", "Flag verdict", ("right", "false_alarm", "not_sure")),
            (
                "would_have_noticed",
                "choice",
                "Would have noticed anyway (self-reported)",
                ("yes", "no", "not_sure"),
            ),
            ("wrongly_blocked", "text", "Wrongly blocked", ()),
        ),
    ),
    (
        "downloads",
        "6. Downloads",
        (
            ("looked_right", "choice", "Downloads looked right", ("yes", "no")),
            ("problems", "text", "Problems", ()),
        ),
    ),
    (
        "overall",
        "7. Overall",
        (
            ("would_use", "choice", "Would use it", ("yes", "maybe", "no")),
            ("would_pay_19", "choice", "Would pay $19", ("yes", "maybe", "no")),
            ("pay_why", "text", "Why (pay)", ()),
            ("fix_first", "text", "Fix first", ()),
            ("quote_ok", "flag", "Quote consent", ()),
        ),
    ),
)

_QUICK_COLUMNS = ("quick.kind", "quick.rating", "quick.text")
_RAW_COLUMN = "raw_answers"  # only filled for a row whose schema_version this code does not know
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def pseudonym(user_id: uuid.UUID, key: bytes, width: int = 6) -> str:
    """Stable per (user, key), not reversible without the key: "T-" + hex digest prefix."""
    return "T-" + hmac.new(key, user_id.bytes, hashlib.sha256).hexdigest()[:width]


def _pseudonyms(records: Sequence[FeedbackRecord], key: bytes) -> dict[uuid.UUID, str]:
    """One pseudonym per tester; widened from 6 to 8 hex chars for everyone on a collision."""
    ids = sorted({r.user_id for r in records}, key=lambda u: u.bytes)
    names: dict[uuid.UUID, str] = {}
    for width in (6, 8):
        names = {uid: pseudonym(uid, key, width) for uid in ids}
        if len(set(names.values())) == len(names):
            break
    return names


def _tester(r: FeedbackRecord, names: dict[uuid.UUID, str], with_emails: bool) -> str:
    return f"{names[r.user_id]} ({r.email})" if with_emails else names[r.user_id]


def _known(r: FeedbackRecord) -> bool:
    return r.schema_version == SCHEMA_VERSION


def _quote(text: str, attribution: str) -> list[str]:
    quoted = [f"> {line}" for line in (text.splitlines() or [""])]
    quoted[-1] += f" -- {attribution}"
    return quoted


def _day(r: FeedbackRecord) -> str:
    return r.created_at.date().isoformat()


def _rating_summary(values: list[int]) -> str:
    if not values:
        return "no answers"
    hist = " ".join(f"{n}:{values.count(n)}" for n in range(1, 6))
    return f"n={len(values)}, mean {sum(values) / len(values):.1f}, {hist}"


def _choice_summary(values: list[str], options: tuple[str, ...]) -> str:
    if not values:
        return "no answers"
    counts = Counter(values)
    parts = [f"{o}: {counts.get(o, 0)}" for o in options]
    parts += [f"{o}: {n}" for o, n in counts.items() if o not in options]
    return ", ".join(parts)


def _quick_lines(
    rows: Sequence[FeedbackRecord], names: dict[uuid.UUID, str], with_emails: bool
) -> list[str]:
    lines: list[str] = []
    for r in rows:
        who = _tester(r, names, with_emails)
        rating = r.answers.get("rating")
        extra = f", rating {rating}" if rating is not None else ""
        text = r.answers.get("text") or "(no text)"
        kind = r.answers.get("kind")
        lines += _quote(str(text), f"{who}, {_day(r)}, quick/{kind} on {r.page_area}{extra}")
    return lines


def render_markdown(
    records: Sequence[FeedbackRecord], *, key: bytes, with_emails: bool = False
) -> str:
    if not records:
        return "No feedback yet.\n"
    names = _pseudonyms(records, key)
    surveys = [r for r in records if _known(r) and r.form == "survey"]
    quicks = [r for r in records if _known(r) and r.form == "quick"]
    days = sorted(_day(r) for r in records)
    out = [
        "# Tester feedback",
        "",
        f"- {len(records)} responses ({len(surveys)} surveys, {len(quicks)} quick) "
        f"from {len(names)} testers",
        f"- {days[0]} to {days[-1]}",
        f"- app versions: {', '.join(sorted({r.app_version for r in records}))}",
        "",
    ]
    for section, title, fields in _SURVEY_SECTIONS:
        out += [f"## {title}", ""]
        answered = [
            (r, r.answers[section]) for r in surveys if isinstance(r.answers.get(section), dict)
        ]
        if not answered:
            out += ["_No survey answers._", ""]
        for field, kind, label, options in fields:
            pairs = [(r, a[field]) for r, a in answered if a.get(field) is not None]
            if kind == "rating":
                out += [f"- {label}: {_rating_summary([int(v) for _, v in pairs])}"]
            elif kind == "choice":
                out += [f"- {label}: {_choice_summary([str(v) for _, v in pairs], options)}"]
            elif kind == "text":
                out += [f"- {label}:"]
                for r, v in pairs:
                    attribution = f"{_tester(r, names, with_emails)}, {_day(r)}, survey"
                    out += [f"  {line}" for line in _quote(str(v), attribution)]
        out += [""]
        areas = SECTION_AREAS.get(section, ())
        mapped = [r for r in quicks if r.page_area in areas]
        if mapped:
            out += [f"Quick feedback ({', '.join(areas)}):", ""]
            out += _quick_lines(mapped, names, with_emails) + [""]
    others = [r for r in quicks if r.page_area == "other"]
    out += ["## Other pages", ""]
    out += (_quick_lines(others, names, with_emails) if others else ["_None._"]) + [""]

    out += ["## Quotable (consented)", ""]
    quotable: list[str] = []
    for r in surveys:
        overall = r.answers.get("overall")
        if not isinstance(overall, dict) or overall.get("quote_ok") is not True:
            continue
        for field in ("fix_first", "pay_why"):
            if overall.get(field):
                attribution = f"{_tester(r, names, with_emails)}, {_day(r)}, {field}"
                quotable += _quote(str(overall[field]), attribution)
    out += (quotable or ["_None._"]) + [""]

    unknown = [r for r in records if not _known(r)]
    if unknown:
        out += ["## Unrecognised", ""]
        for r in unknown:
            raw = json.dumps(r.answers, sort_keys=True, ensure_ascii=False)
            who = _tester(r, names, with_emails)
            out += [f"- {r.id} schema_version={r.schema_version} {who}: {raw}"]
        out += [""]
    return "\n".join(out).rstrip("\n") + "\n"


def _cell(value: object) -> str:
    if value is None:
        return ""
    text = "true" if value is True else "false" if value is False else str(value)
    # Spreadsheet formula injection: Excel/Sheets evaluate a cell that opens with one of these.
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def render_csv(records: Sequence[FeedbackRecord], *, key: bytes, with_emails: bool = False) -> str:
    names = _pseudonyms(records, key)
    survey_cols = [(s, f[0]) for s, _, fields in _SURVEY_SECTIONS for f in fields]
    header = ["id", "tester"] + (["email"] if with_emails else [])
    header += ["created_at", "form", "page_area", "app_version", "job_id", "package_id"]
    header += [f"{s}.{f}" for s, f in survey_cols] + list(_QUICK_COLUMNS)
    header.append(_RAW_COLUMN)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for r in records:
        row: list[object] = [r.id, names[r.user_id]] + ([r.email] if with_emails else [])
        row += [r.created_at.isoformat(), r.form, r.page_area, r.app_version]
        row += [r.job_id, r.package_id]
        known = _known(r)
        for section, field in survey_cols:
            data = r.answers.get(section) if known and r.form == "survey" else None
            row.append(data.get(field) if isinstance(data, dict) else None)
        for column in _QUICK_COLUMNS:
            field = column.split(".", 1)[1]
            row.append(r.answers.get(field) if known and r.form == "quick" else None)
        row.append(None if known else json.dumps(r.answers, sort_keys=True, ensure_ascii=False))
        writer.writerow([_cell(v) for v in row])
    return buffer.getvalue()
