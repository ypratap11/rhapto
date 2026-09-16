from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rhapto.db.base import Base, TimestampMixin, UserScopedMixin, new_uuid

EMBEDDING_DIMENSIONS = 384
APPLICATION_STATUSES = ("discovered", "queued", "applied", "screen", "interview", "offer", "closed")
APPLIED_STATUSES = ("applied", "screen", "interview", "offer", "closed")
TASK_STATUSES = ("queued", "running", "succeeded", "failed")
# draft: written, not yet reviewed. ready: a human reviewed it and it may be applied with.
# blocked: guardrails refused it. A package is never written as "ready" -- only promoted.
PACKAGE_STATUSES = ("draft", "ready", "blocked")
CLOSED_REASONS = ("rejected", "withdrew", "no_response", "filled")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResumeBlock(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "resume_blocks"
    __table_args__ = (UniqueConstraint("user_id", "block_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    block_id: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    org: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    period: Mapped[str | None] = mapped_column(String(50))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metric: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    attribution: Mapped[str | None] = mapped_column(String(200))
    concurrent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclude_when: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class ResumeBase(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "resume_bases"
    __table_args__ = (UniqueConstraint("user_id", "base_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    block_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    section_order: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    style_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Track(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("user_id", "track_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    resume_base: Mapped[str] = mapped_column(String(100), nullable=False)
    min_fit: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Where this track came from in packages/schemas/taxonomy.yaml. NULL on tracks written by
    # hand or imported from a tracks.yaml that predates the picker, which is why the Field
    # filter treats NULL as "not in any field" rather than guessing.
    field: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str | None] = mapped_column(String(50))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class Guardrail(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "guardrails"
    __table_args__ = (UniqueConstraint("user_id", "rule"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Answers(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    answers_json: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)


class ResumeDocumentRow(UserScopedMixin, TimestampMixin, Base):
    """The one resume DOCX the user uploaded for tune mode.

    Only the parsed form lives here; the bytes stay on the storage volume (`path`) because a
    multi-megabyte upload has no business in a JSON column. One row per user: re-uploading
    replaces it, which is why `user_id` is unique.
    """

    __tablename__ = "resume_documents"
    __table_args__ = (UniqueConstraint("user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LlmSettingsRow(UserScopedMixin, TimestampMixin, Base):
    """The user's chosen LLM provider, model, and encrypted API key.

    One row per user (hence the unique `user_id`): the UI offers a single active provider, and a
    second row would leave "which key do we call?" undefined. The key is stored Fernet-encrypted by
    `services.secrets`; nothing here ever holds plaintext.
    """

    __tablename__ = "llm_settings"
    __table_args__ = (UniqueConstraint("user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)


class WatchlistEntry(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "watchlist"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    board: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}", nullable=False
    )
    #: True once a poll on this board has actually returned a job (as opposed to the entry
    #: existing but never having matched anything yet).
    discovered: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )


class Job(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    best_track_id: Mapped[str | None] = mapped_column(String(100))
    best_fit: Mapped[int | None] = mapped_column(Integer)
    # How this posting's location read against the user's answers.yaml preference when it was
    # last scored: one of preferred/remote/country/abroad/unknown. NULL on rows written before
    # location priority existed, and on rows the scorer has not reached yet.
    location_tier: Mapped[str | None] = mapped_column(String(12))
    repost_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    rescued: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    identity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL")
    )
    # "Not interested": the job leaves the grid's default view, recommendations and the Resumes
    # queue. The row stays, so a later repost can still point at it.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once the source stopped returning this posting on UNLISTED_AFTER consecutive polls.
    unlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Whatever the source said about pay, verbatim; NULL when it said nothing. Never computed.
    salary_text: Mapped[str | None] = mapped_column(String(200))
    # Consecutive polls of this job's own source and scope that did not return its external id.
    # A smallint because it never exceeds UNLISTED_AFTER before the row is marked and reset.
    miss_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )


class Package(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "packages"
    __table_args__ = (UniqueConstraint("job_id", "version"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    resume_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cover_note: Mapped[str] = mapped_column(Text, nullable=False)
    change_log: Mapped[str] = mapped_column(Text, nullable=False)
    answers_json: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    guardrail_report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    jd_extract_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    selection_block_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, nullable=False
    )
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    docx_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    parent_package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL")
    )
    # Tune mode: the edits applied to the user's own document, and the document they were
    # applied to. NULL on every package written before tune mode existed, which is why the
    # readers default rather than assume.
    mode: Mapped[str] = mapped_column(
        String(10), default="blocks", server_default="blocks", nullable=False
    )
    edits_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    source_document_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # "Skip": the draft leaves the Resumes queue. Kept, not deleted, so the change log survives.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Application(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        # A reason only means something on a closed application; the router clears it when a
        # closed application is reopened, and this makes the invariant the database's.
        CheckConstraint(
            "closed_reason IS NULL OR status = 'closed'", name="ck_applications_closed_reason"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("packages.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status_history_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    closed_reason: Mapped[str | None] = mapped_column(String(20))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(String(100))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Aggregator(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "aggregators"
    __table_args__ = (UniqueConstraint("user_id", "source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default="{}", nullable=False
    )


class JobScore(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "job_scores"
    __table_args__ = (UniqueConstraint("job_id", "track_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PollRun(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "poll_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    board: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    new: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL")
    )


REMOTE_VALUES = ("include", "only", "exclude")


class SearchRow(UserScopedMixin, TimestampMixin, Base):
    """One saved search: what to ask every enabled aggregator for, on the normal schedule."""

    __tablename__ = "searches"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    remote: Mapped[str] = mapped_column(
        String(10), default="include", server_default="include", nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    #: The track this search was derived from, until the user edits its criteria.
    derived_from_track_id: Mapped[str | None] = mapped_column(String(100))
    # When the user last opened this search's results; "N new" counts jobs discovered after it.
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceCredentialRow(UserScopedMixin, TimestampMixin, Base):
    """The user's key(s) for one keyed aggregator, Fernet-encrypted as one JSON object."""

    __tablename__ = "source_credentials"
    __table_args__ = (UniqueConstraint("user_id", "source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
