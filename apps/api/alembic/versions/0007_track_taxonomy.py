"""tracks remember which taxonomy field and role created them

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("field", sa.String(length=50), nullable=True))
    op.add_column("tracks", sa.Column("role", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tracks", "role")
    op.drop_column("tracks", "field")
