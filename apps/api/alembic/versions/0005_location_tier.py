"""location_tier: how a posting's location read against the user's preference

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("location_tier", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "location_tier")
