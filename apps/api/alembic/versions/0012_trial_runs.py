"""trial_runs_used on users: a monotone count of runs spent on the DEPLOYMENT's provider key

Revision ID: 0012
Revises: 0011

One additive column and one CHECK constraint. Nothing else changes; `packages` is untouched.

Why a counter on `users` rather than a count of `packages` rows (the mechanism the functional spec
proposed and the architect rejected): a spend bound has to be a record of spend -- monotone, out of
reach of any user-facing delete, written before the money leaves, and attributed to the key that
paid. `packages` is none of those. `PATCH /packages/{id}` writes a new row carrying the parent's
`llm_model` while making no model call (so a human edit in the review queue would consume a paid
run), `DELETE /jobs/{id}` cascades its packages away (so the count is resettable by an ordinary
product action, one HTTP call, unbounded), a run that dies after its first billed call leaves no row
at all, and `llm_model` records the adapter object rather than the spend -- the free fake provider
writes a model id, and the fake every test uses writes NULL.

**No backfill and no data migration.** `server_default "0"` gives both existing accounts a fresh
allowance, which is exactly the spec's "no retroactive charging or accounting of the 34 runs already
made". The owner's account is exempt anyway: he has a stored key of his own, and the counter only
ever moves for a run that resolves to the deployment's key.

Reversible: `downgrade()` drops the constraint and the column. Dropping the column discards the
counts, so a downgrade followed by a re-upgrade hands every account a fresh allowance -- which errs
toward the user, not the maintainer, and is the same position a fresh install starts from.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "trial_runs_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    # The repo's habit of making an invariant the database's (cf. ck_applications_closed_reason).
    # `claim_trial_run`'s WHERE cannot go below zero, so this constraint guards a hand-written
    # UPDATE -- the documented way an operator resets someone's allowance.
    op.create_check_constraint("ck_users_trial_runs_used", "users", "trial_runs_used >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_users_trial_runs_used", "users", type_="check")
    op.drop_column("users", "trial_runs_used")
