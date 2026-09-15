"""saved searches, source credentials, discovered boards

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("remote", sa.String(length=10), nullable=False, server_default="include"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("derived_from_track_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_credentials",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "source", name="uq_source_credentials_user_source"),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "search_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("searches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "poll_runs",
        sa.Column(
            "search_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("searches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "watchlist",
        sa.Column("discovered", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("watchlist", "discovered")
    op.drop_column("poll_runs", "search_id")
    op.drop_column("jobs", "search_id")
    op.drop_table("source_credentials")
    op.drop_table("searches")
