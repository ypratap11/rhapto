"""discovery: job scoring columns, aggregators, job_scores, poll_runs

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("external_id", sa.String(length=200), nullable=True))
    op.add_column("jobs", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("best_track_id", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("best_fit", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("repost_of", sa.Uuid(), nullable=True))
    op.add_column(
        "jobs", sa.Column("rescued", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column("jobs", sa.Column("identity_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key("fk_jobs_repost_of", "jobs", "jobs", ["repost_of"], ["id"], ondelete="SET NULL")
    op.create_index("ix_jobs_identity_hash", "jobs", ["identity_hash"])
    op.create_index(
        "uq_jobs_user_source_external",
        "jobs",
        ["user_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.add_column(
        "tracks",
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    )
    op.add_column(
        "watchlist",
        sa.Column(
            "keywords", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False
        ),
    )
    op.create_table(
        "aggregators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source"),
    )
    op.create_index("ix_aggregators_user_id", "aggregators", ["user_id"])
    op.create_table(
        "job_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.String(length=100), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("rationale_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "track_id"),
    )
    op.create_index("ix_job_scores_user_id", "job_scores", ["user_id"])
    op.create_index("ix_job_scores_job_id", "job_scores", ["job_id"])
    op.create_table(
        "poll_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("board", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poll_runs_user_id", "poll_runs", ["user_id"])
    op.create_index(
        "ix_poll_runs_lookup", "poll_runs", ["user_id", "source", "board", sa.text("started_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("poll_runs")
    op.drop_table("job_scores")
    op.drop_table("aggregators")
    op.drop_column("watchlist", "keywords")
    op.drop_column("tracks", "embedding")
    op.drop_index("uq_jobs_user_source_external", table_name="jobs")
    op.drop_index("ix_jobs_identity_hash", table_name="jobs")
    op.drop_constraint("fk_jobs_repost_of", "jobs", type_="foreignkey")
    for name in ("identity_hash", "rescued", "repost_of", "best_fit", "best_track_id", "posted_at", "external_id"):
        op.drop_column("jobs", name)
