"""tune mode: resume_documents table, package mode/edits/source document

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resume_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("parsed_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_resume_documents_user_id", "resume_documents", ["user_id"])
    op.add_column(
        "packages",
        sa.Column("mode", sa.String(length=10), server_default="blocks", nullable=False),
    )
    op.add_column(
        "packages", sa.Column("edits_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "packages",
        sa.Column("source_document_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("packages", "source_document_json")
    op.drop_column("packages", "edits_json")
    op.drop_column("packages", "mode")
    op.drop_index("ix_resume_documents_user_id", table_name="resume_documents")
    op.drop_table("resume_documents")
