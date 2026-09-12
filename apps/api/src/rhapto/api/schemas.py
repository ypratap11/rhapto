from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from rhapto.db.models import APPLICATION_STATUSES
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument
from rhapto.models.source_document import Edit, SourceDocument


class HealthOut(BaseModel):
    status: str


class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID


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
    rescued: bool = False
    repost_of: uuid.UUID | None = None
    posted_at: datetime | None = None
    scores: list[JobScoreOut] = []


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
    """A human edit to a package: `resume` in blocks mode, `edits` in tune mode.

    Each field carries the complete new state for its mode, not a delta, so a new version is
    always a full replacement of the thing the mode owns.
    """

    resume: ResumeDocument | None = None
    edits: list[EditPatch] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> PackagePatch:
        if (self.resume is None) == (self.edits is None):
            raise ValueError("provide exactly one of resume or edits")
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
    status: str | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
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


class SourceInfoOut(BaseModel):
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool
