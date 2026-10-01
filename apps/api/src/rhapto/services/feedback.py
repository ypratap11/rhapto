"""Tester feedback: the answer schemas (the only writer's contract) and, later, the owner report.

Pure module: imports pydantic and the standard library only, so the API router and the CLI share one
definition (`services-do-not-import-entrypoints` holds).

Free text is validated here, not left to Postgres: `jsonb` refuses U+0000 with a DataError that would
surface as a 500, and a 500 is the one path that logs. The validator's message never quotes the value.
"""

from __future__ import annotations

from typing import Annotated, Literal

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
    if any(ord(ch) < 0x20 and ch not in _ALLOWED_CONTROLS for ch in value):
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
