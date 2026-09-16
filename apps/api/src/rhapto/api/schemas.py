from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rhapto.db.models import APPLICATION_STATUSES, CLOSED_REASONS
from rhapto.engine.scoring import LocationTier
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument
from rhapto.models.source_document import Edit, SourceDocument


class HealthOut(BaseModel):
    status: str


class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID
    # False when neither Settings nor the environment yields a usable provider key: the web app
    # uses it to point the user at Settings before they try to tailor anything.
    llm_configured: bool


class ProviderInfoOut(BaseModel):
    """One supported provider, for the Settings picker."""

    id: str
    label: str
    models: list[str]
    default: str


class LlmSettingsOut(BaseModel):
    """What the user's LLM is right now. The key itself never leaves the server: only whether one
    is set, and its last four characters so the user can tell which key it is."""

    provider: str | None
    model: str | None
    key_set: bool
    key_hint: str | None
    source: Literal["settings", "env", "none"]
    providers: list[ProviderInfoOut]


# `llm_settings.model` is String(100) and `provider` is a registry id, so anything longer is a
# typo or a probe. Bounding it here makes it a 422 naming the field; without the bound an over-long
# model id reaches the INSERT and comes back as an opaque 500 (varchar truncation is a DBAPIError,
# not an IntegrityError, so nothing but the last-resort handler catches it).
ModelIdIn = Field(min_length=1, max_length=100)
ProviderIdIn = Field(max_length=20)


class LlmSettingsIn(BaseModel):
    provider: str = ProviderIdIn
    model: str = ModelIdIn
    # Omitted means "keep the key I already have" (or the environment's, for this provider).
    api_key: str | None = None


class LlmTestIn(BaseModel):
    provider: str = ProviderIdIn
    model: str = ModelIdIn
    api_key: str | None = None


class LlmTestOut(BaseModel):
    ok: bool
    model: str | None = None
    error: str | None = None


class ImportOut(BaseModel):
    blocks: int
    tracks: int
    bases: int
    guardrails: int


class JobCreate(BaseModel):
    jd_text: str | None = None
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> JobCreate:
        if bool(self.jd_text) == bool(self.url):
            raise ValueError("provide exactly one of jd_text or url")
        if self.jd_text is not None and len(self.jd_text.strip()) < 50:
            raise ValueError("jd_text must be at least 50 characters")
        return self


class PackageSummary(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    # The queue renders the mode chip from here, so "which mode produced this draft" is answerable
    # without fetching the package. Normalised on the way out, as the package endpoints do, so an
    # old row written before tune mode existed reads as "blocks".
    mode: Literal["blocks", "tune"]
    created_at: datetime


class JobScoreOut(BaseModel):
    track_id: str
    fit_score: int
    rationale: dict[str, Any]


class JobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str | None
    title: str | None
    location: str | None
    url: str | None
    jd_text: str
    extracted: JDExtract | None
    discovered_at: datetime
    latest_package: PackageSummary | None
    application_status: str | None
    best_track_id: str | None = None
    best_fit: int | None = None
    bucket: Literal["fit", "low"] | None = None
    location_tier: LocationTier | None = None
    rescued: bool = False
    repost_of: uuid.UUID | None = None
    posted_at: datetime | None = None
    scores: list[JobScoreOut] = []
    # The saved search that discovered this job, for display; None for manually-added jobs and
    # for board runs that carry no search. Left-joined in `jobs.list_jobs`.
    search_name: str | None = None
    # Not populated until Task 9 adds the column; declared now so the generated TypeScript
    # settles once.
    salary_text: str | None = None
    # "Not interested" / "no longer listed"; see Job.hidden_at and Job.unlisted_at.
    hidden_at: datetime | None = None
    unlisted_at: datetime | None = None


class TailorBody(BaseModel):
    track_id: str | None = None
    feedback: str | None = None
    parent_package_id: uuid.UUID | None = None
    # None means "pick for me": tune when the user has uploaded a resume document, blocks
    # otherwise. An explicit value always wins, so a user with a document can still run the
    # block library against a job.
    mode: Literal["blocks", "tune"] | None = None


class PackageOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    track_id: str
    version: int
    status: str
    resume: ResumeDocument
    cover_note: str
    change_log: str
    answers: dict[str, str]
    guardrail_report: GuardrailReport
    jd_extract: JDExtract
    llm_calls: int
    parent_package_id: uuid.UUID | None
    has_docx: bool
    has_pdf: bool
    created_at: datetime
    mode: Literal["blocks", "tune"]
    edits: list[Edit]
    source_document: SourceDocument | None


class EditPatch(BaseModel):
    """One paragraph the human rewrote. `before` is not accepted: the stored document is the
    only authority on what the paragraph said."""

    paragraph_id: str
    after: str


class PackagePatch(BaseModel):
    """A human action on a package: `resume` in blocks mode, `edits` in tune mode, or `status`.

    Each field carries the complete new state for its mode, not a delta, so a new version is
    always a full replacement of the thing the mode owns. `status` is the odd one out: it changes
    the existing row in place and creates no version, because "I have read this and it is ready"
    is a fact about the draft that already exists, not a new draft.

    `blocked` is not settable: it is the guardrail validator's verdict, not a human's.
    """

    resume: ResumeDocument | None = None
    edits: list[EditPatch] | None = None
    status: Literal["ready", "draft"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> PackagePatch:
        given = [f for f in (self.resume, self.edits, self.status) if f is not None]
        if len(given) != 1:
            raise ValueError("provide exactly one of resume, edits or status")
        return self


class PackageListItem(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    company: str | None
    title: str | None
    version: int
    status: str
    mode: Literal["blocks", "tune"]
    application_status: str | None
    best_fit: int | None
    best_track_id: str | None
    created_at: datetime
    archived_at: datetime | None = None


class ResumeDocumentOut(BaseModel):
    filename: str
    uploaded_at: datetime
    document: SourceDocument


class StatusChange(BaseModel):
    status: str
    at: datetime


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    package_id: uuid.UUID | None = None


class ApplicationPatch(BaseModel):
    """A partial update. An omitted field is left alone; an explicit null clears it, which is
    why the router reads `model_dump(exclude_unset=True)` rather than testing for None."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    notes: str | None = None
    closed_reason: str | None = None
    follow_up_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
        return value

    @field_validator("closed_reason")
    @classmethod
    def _known_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in CLOSED_REASONS:
            raise ValueError(f"closed_reason must be one of {', '.join(CLOSED_REASONS)}")
        return value


class JobRef(BaseModel):
    id: uuid.UUID
    company: str | None
    title: str | None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job: JobRef
    package_id: uuid.UUID | None
    status: str
    applied_at: datetime | None
    notes: str
    status_history: list[StatusChange]
    created_at: datetime
    updated_at: datetime
    closed_reason: str | None = None
    follow_up_at: datetime | None = None


class BoardOut(BaseModel):
    columns: dict[str, list[ApplicationOut]]


class TaskOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    progress: dict[str, Any]
    error: str | None
    result_ref: str | None
    created_at: datetime
    finished_at: datetime | None


class PollRunOut(BaseModel):
    id: uuid.UUID
    source: str
    board: str | None
    started_at: datetime
    finished_at: datetime | None
    found: int
    new: int
    error: str | None
    # Which saved search drove this run, for a keyless aggregator fanned out across several
    # searches (see services.discovery.poller). None for a board run.
    search_id: uuid.UUID | None = None


class SourceInfoOut(BaseModel):
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool


RemoteValue = Literal["include", "only", "exclude"]


class SearchIn(BaseModel):
    """What the form sends: either the one phrase the user typed, or an explicit keyword list.

    The search box has a single input, so `query` is the common case and `name` follows from it;
    the Searches tab edits the keyword list directly. Accepting both at once would leave "what
    is this search actually looking for" ambiguous, so exactly one is required.
    """

    name: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=200)
    keywords: list[str] | None = Field(default=None, max_length=10)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    active: bool = True

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SearchIn:
        if (self.query is None) == (self.keywords is None):
            raise ValueError("provide exactly one of query or keywords")
        if self.query is not None and not self.query.strip():
            raise ValueError("query must not be blank")
        if self.keywords is not None:
            cleaned = [k.strip() for k in self.keywords if k.strip()]
            if not cleaned or any(len(k) > 60 for k in cleaned):
                raise ValueError("each keyword must be 1-60 characters")
        return self

    @property
    def resolved_keywords(self) -> list[str]:
        if self.keywords is not None:
            return [k.strip() for k in self.keywords if k.strip()]
        return [(self.query or "").strip()]

    @property
    def resolved_name(self) -> str:
        return ((self.name or "").strip() or self.resolved_keywords[0])[:100]


class SearchOut(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    location: str | None
    remote: RemoteValue
    active: bool
    derived_from_track_id: str | None
    created_at: datetime
    last_viewed_at: datetime | None = None
    #: Jobs this search found since `last_viewed_at`, excluding hidden and unlisted ones.
    new_count: int = 0


class SourceSettingOut(BaseModel):
    id: str
    label: str
    needs_key: bool
    fields: list[str]
    enabled: bool
    key_set: bool


class SourceSettingIn(BaseModel):
    enabled: bool
    #: Omitted fields keep whatever is stored; the values never come back out.
    credentials: dict[str, str] | None = None


class SourceTestOut(BaseModel):
    ok: bool
    found: int | None = None
    error: str | None = None


class LiveSearchIn(BaseModel):
    """The search form: one free-text query plus the filter chips."""

    query: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    field: str | None = Field(default=None, max_length=50)
    posted_within: Literal["24h", "7d", "30d", "any"] = "any"
    #: None means every enabled source; a list narrows the fan-out to those source ids.
    sources: list[str] | None = None


class PerSourceOut(BaseModel):
    found: int
    new: int
    error: str | None = None


class LiveSearchOut(BaseModel):
    jobs: list[JobOut]
    #: Keyed by source id, so the UI can say which vendor was slow or needs a key.
    per_source: dict[str, PerSourceOut]


class TaxonomySuggestionOut(BaseModel):
    """One role the uploaded resume's entry titles point at, for the picker's chip row."""

    field_id: str
    field_name: str
    role_id: str
    role_name: str
    matched_title: str


class ChecklistOut(BaseModel):
    """Six setup tests plus the verified-block tally, rendered as "18 of 23 verified"."""

    resume_template: bool
    contact_answers: bool
    tracks: bool
    blocks_verified: bool
    guardrails: bool
    location_preferences: bool
    verified_blocks: int
    total_blocks: int


class SavedSearchCountOut(BaseModel):
    id: uuid.UUID
    name: str
    new_count: int


class FollowUpOut(BaseModel):
    application_id: uuid.UUID
    job: JobRef
    status: str
    follow_up_at: datetime


class DashboardOut(BaseModel):
    new_fit_count: int
    needs_review_count: int
    checklist: ChecklistOut
    saved_searches: list[SavedSearchCountOut]
    due_followups: list[FollowUpOut]
