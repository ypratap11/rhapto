"""tenancy fixes: unique constraints on applications, watchlist, job_scores and packages

Revision ID: 0010
Revises: 0009

Phase 0 items 3 and 4 of the tenancy remediation, as one migration:

* `UNIQUE(user_id, job_id)` on `applications` -- a duplicate application for the same job fans
  out the outer join in `needs_review_count` and double-counts it on the dashboard.
* `UNIQUE(user_id, source, board)` on `watchlist` -- paired with `ON CONFLICT DO NOTHING` on the
  poller's `_discover_boards` insert, this stops the same board being re-added (and re-polled)
  every time a job from it resurfaces.
* `UNIQUE(user_id, job_id, track_id)` on `job_scores` and `UNIQUE(user_id, job_id, version)` on
  `packages`, replacing their current `(job_id, ...)`-only constraints -- correct on their own
  merits today, and the last moment they are a relabel rather than a merge under either
  architecture on the table for Phase 1.

Each `UNIQUE` is preceded by a duplicate check that fails loudly, naming the offending keys,
rather than letting `CREATE UNIQUE INDEX` fail with Postgres's own opaque "could not create
unique index" error. There is one user in production today (1,430 jobs, 52 packages), so none of
these are expected to find anything.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fail_on_duplicates(table: str, columns: list[str]) -> None:
    """Raise, naming the offending keys, if `table` has more than one row for any `columns` tuple.

    A `RuntimeError` here aborts the migration inside its transaction, so nothing is left
    half-migrated; the operator resolves the listed rows by hand and re-runs `alembic upgrade`.
    """
    conn = op.get_bind()
    col_list = ", ".join(columns)
    rows = conn.execute(
        sa.text(
            f"SELECT {col_list}, COUNT(*) AS n FROM {table} "  # noqa: S608 (table/cols are literals below, not input)
            f"GROUP BY {col_list} HAVING COUNT(*) > 1 LIMIT 10"
        )
    ).fetchall()
    if rows:
        raise RuntimeError(
            f"refusing to add UNIQUE({col_list}) on {table}: duplicate rows exist "
            f"(showing up to 10, as ({col_list}, count)): {[tuple(r) for r in rows]}. "
            "Resolve them by hand -- merge or delete the extras -- then re-run this migration."
        )


def upgrade() -> None:
    _fail_on_duplicates("applications", ["user_id", "job_id"])
    op.create_unique_constraint(
        "uq_applications_user_id_job_id", "applications", ["user_id", "job_id"]
    )

    _fail_on_duplicates("watchlist", ["user_id", "source", "board"])
    op.create_unique_constraint(
        "uq_watchlist_user_id_source_board", "watchlist", ["user_id", "source", "board"]
    )

    _fail_on_duplicates("job_scores", ["user_id", "job_id", "track_id"])
    op.drop_constraint("job_scores_job_id_track_id_key", "job_scores", type_="unique")
    op.create_unique_constraint(
        "uq_job_scores_user_id_job_id_track_id",
        "job_scores",
        ["user_id", "job_id", "track_id"],
    )

    _fail_on_duplicates("packages", ["user_id", "job_id", "version"])
    op.drop_constraint("packages_job_id_version_key", "packages", type_="unique")
    op.create_unique_constraint(
        "uq_packages_user_id_job_id_version", "packages", ["user_id", "job_id", "version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_packages_user_id_job_id_version", "packages", type_="unique")
    op.create_unique_constraint("packages_job_id_version_key", "packages", ["job_id", "version"])

    op.drop_constraint("uq_job_scores_user_id_job_id_track_id", "job_scores", type_="unique")
    op.create_unique_constraint(
        "job_scores_job_id_track_id_key", "job_scores", ["job_id", "track_id"]
    )

    op.drop_constraint("uq_watchlist_user_id_source_board", "watchlist", type_="unique")

    op.drop_constraint("uq_applications_user_id_job_id", "applications", type_="unique")
