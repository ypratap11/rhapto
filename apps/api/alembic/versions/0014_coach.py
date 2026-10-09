"""coach: first-import-free flag, the coach step-event table and the track scoring marker

Revision ID: 0014
Revises: 0013

Additive: three columns and one new, empty table. Every existing user starts with `free_import_used_at`
NULL, so each gets exactly one free resume import even if they imported before (accepted, spec 3.2).

`tracks.score_requested_at` (set by every track save) and `tracks.scored_at` (set by a rescore that
started after that save) make "this track is fully scored" a fact the coach can ask for (spec 3.3).
The one data statement: existing tracks are marked scored (`scored_at = now()`, the same transaction
instant as the default of `score_requested_at`), because their scores already exist.

`coach_events.day` is the UTC calendar day, stored (not derived from `created_at`) because
`created_at::date` on a timestamptz is not IMMUTABLE and Postgres will not index it.
`UNIQUE (user_id, step, day)` makes the fire-and-forget client idempotent per day.

**Downgrade drops the column and every coach event.** There is no copy. Take `scripts/backup-db.sh`
first if any of it matters.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STEPS = ("started", "resume_in", "role_confirmed", "jobs_shown", "tailor_started", "downloaded")


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("free_import_used_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "coach_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=False),
        sa.Column(
            "day",
            sa.Date(),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')::date"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "step IN (" + ", ".join(f"'{s}'" for s in STEPS) + ")", name="ck_coach_events_step"
        ),
        sa.UniqueConstraint("user_id", "step", "day", name="uq_coach_events_user_step_day"),
    )
    op.create_index("ix_coach_events_user_id", "coach_events", ["user_id"])
    op.add_column(
        "tracks",
        sa.Column(
            "score_requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column("tracks", sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tracks SET scored_at = now()")


def downgrade() -> None:
    """Drops the table, every coach event in it, the free-import flag and the track scoring marker."""
    op.drop_column("tracks", "scored_at")
    op.drop_column("tracks", "score_requested_at")
    op.drop_index("ix_coach_events_user_id", table_name="coach_events")
    op.drop_table("coach_events")
    op.drop_column("users", "free_import_used_at")
