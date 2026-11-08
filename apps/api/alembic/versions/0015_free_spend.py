"""free_spend: append-only ledger of model calls paid for by the deployment's key

Revision ID: 0015
Revises: 0014

Additive: one new, empty table. The month's free spend is the sum of `cost_usd` since the start of
the UTC calendar month, computed in SQL.

`user_id` is a plain UUID with no foreign key, on purpose: deleting a user or a job must not lower
the month's spend.

**Downgrade drops the table and the whole ledger.** There is no copy. Take `scripts/backup-db.sh`
first if any of it matters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "free_spend",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "cache_creation_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("cost_usd >= 0", name="ck_free_spend_cost_usd"),
    )
    op.create_index("ix_free_spend_user_id", "free_spend", ["user_id"])
    op.create_index("ix_free_spend_created_at", "free_spend", ["created_at"])


def downgrade() -> None:
    """Drops the table and every ledger row in it."""
    op.drop_index("ix_free_spend_created_at", table_name="free_spend")
    op.drop_index("ix_free_spend_user_id", table_name="free_spend")
    op.drop_table("free_spend")
