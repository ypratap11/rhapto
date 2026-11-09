"""admin: users.blocked_at and the admin_actions audit table

Revision ID: 0016
Revises: 0015

Additive: one nullable column (no default, so no table rewrite) and one new, empty table.

`SET LOCAL lock_timeout` comes first: ADD COLUMN needs ACCESS EXCLUSIVE on `users`, and while it
waits behind a long reader every other query on `users` queues behind it. Failing after 10 s is
better than stalling sign-in. `alembic/env.py` runs the migration in one transaction, so SET LOCAL
covers it.

`admin_actions.target_user_id` is a plain UUID with no foreign key, on purpose: deleting a user must
not erase the record of what the owner did to them.

**Downgrade drops the audit table and every row in it, then the column.** Take
`scripts/backup-db.sh` first if any of it matters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '10s'")
    op.add_column("users", sa.Column("blocked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("actor_email", sa.String(length=320), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("before_json", postgresql.JSONB(), nullable=False),
        sa.Column("after_json", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action IN ('reset_runs','block','unblock')", name="ck_admin_actions_action"
        ),
    )
    op.create_index(
        "ix_admin_actions_target_created", "admin_actions", ["target_user_id", "created_at"]
    )


def downgrade() -> None:
    """Drops the audit table and every row in it, then the column."""
    op.drop_index("ix_admin_actions_target_created", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_column("users", "blocked_at")
