"""flow state: hidden, unlisted, archived, closed reasons, follow-ups, salary, last viewed

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLOSED_REASON_CHECK = "closed_reason IS NULL OR status = 'closed'"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("unlisted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("salary_text", sa.String(length=200), nullable=True))
    op.add_column(
        "jobs", sa.Column("miss_count", sa.SmallInteger(), nullable=False, server_default="0")
    )
    op.add_column("packages", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("applications", sa.Column("closed_reason", sa.String(length=20), nullable=True))
    op.add_column(
        "applications", sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_applications_closed_reason", "applications", CLOSED_REASON_CHECK
    )
    op.add_column(
        "searches", sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("searches", "last_viewed_at")
    op.drop_constraint("ck_applications_closed_reason", "applications", type_="check")
    op.drop_column("applications", "follow_up_at")
    op.drop_column("applications", "closed_reason")
    op.drop_column("packages", "archived_at")
    op.drop_column("jobs", "miss_count")
    op.drop_column("jobs", "salary_text")
    op.drop_column("jobs", "unlisted_at")
    op.drop_column("jobs", "hidden_at")
