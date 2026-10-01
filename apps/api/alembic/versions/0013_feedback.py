"""feedback: one insert-only table of tester responses

Revision ID: 0013
Revises: 0012

Purely additive: a new, empty table. No existing table is locked, rewritten or backfilled.

`job_id` / `package_id` are plain UUID columns with no foreign key, on purpose: feedback must outlive
a job the tester later deletes. `user_id` cascades, so deleting an account deletes its feedback.

**Downgrade destroys all collected feedback.** It drops the table; there is no copy. Take
`scripts/backup-db.sh` first if any of it matters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("form", sa.String(length=10), nullable=False),
        sa.Column("page_area", sa.String(length=20), nullable=True),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("app_version", sa.String(length=64), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("form IN ('survey', 'quick')", name="ck_feedback_form"),
        sa.CheckConstraint(
            "page_area IS NULL OR page_area IN ('dashboard', 'jobs', 'job_detail', 'review', "
            "'resumes', 'pipeline', 'profile', 'settings', 'other')",
            name="ck_feedback_page_area",
        ),
        sa.CheckConstraint(
            "(form = 'quick') = (page_area IS NOT NULL)", name="ck_feedback_area_iff_quick"
        ),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_user_created", "feedback", ["user_id", "created_at"])


def downgrade() -> None:
    """Drops the table and every feedback row in it."""
    op.drop_index("ix_feedback_user_created", table_name="feedback")
    op.drop_index("ix_feedback_user_id", table_name="feedback")
    op.drop_table("feedback")
