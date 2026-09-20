"""package token usage: input/output/cache tokens and the model that produced them

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "packages",
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "packages",
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "packages",
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "packages",
        sa.Column("cache_creation_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("packages", sa.Column("llm_model", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("packages", "llm_model")
    op.drop_column("packages", "cache_creation_tokens")
    op.drop_column("packages", "cache_read_tokens")
    op.drop_column("packages", "output_tokens")
    op.drop_column("packages", "input_tokens")
