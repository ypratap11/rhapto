"""user lifecycle columns: idp_subject, last_seen_at, exempt_from_pruning, seeded_at

Revision ID: 0011
Revises: 0010

Four additive columns on `users`, needed by Phase A identity (`idp_subject`, looked up by A3's
access-mode principal resolution -- never used as the lookup key, `email` is, because Access can
reissue a `sub` across an IdP change while the email stays stable; `seeded_at`, Task 5's idempotency
marker for the first-screen backfill) and Phase B lifecycle (`last_seen_at`, `exempt_from_pruning`,
not read by any code until Task 6/7). Bundled into one migration because they are all additive,
metadata-only changes to the same table, and the architecture places the first three together;
`seeded_at` rides along rather than opening a second migration for one nullable column.

`last_seen_at` defaults to `now()`, which backfills every existing row (the owner's account) to "seen
now" -- correct, not a bug: it grants a fresh 90 days from the moment this migration runs, rather than
making the owner's account eligible for pruning on day one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("idp_subject", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_idp_subject", "users", ["idp_subject"])
    op.add_column(
        "users",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "exempt_from_pruning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True))
    # Fixes re-review finding 5: without this, every pre-existing row (the owner's account, on
    # this branch) has seeded_at IS NULL, and Task 5's POST /me/bootstrap treats NULL as "not yet
    # seeded" -- so the owner's first authenticated request after this migration would run
    # backfill_public_jobs *against his own account*, an unplanned write to exactly the data AC 15
    # exists to protect. Backfilling every existing row to "already seeded" is correct: an
    # already-populated account has nothing this backfill would add anyway.
    op.execute("UPDATE users SET seeded_at = now() WHERE seeded_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "seeded_at")
    op.drop_column("users", "exempt_from_pruning")
    op.drop_column("users", "last_seen_at")
    op.drop_constraint("uq_users_idp_subject", "users", type_="unique")
    op.drop_column("users", "idp_subject")
