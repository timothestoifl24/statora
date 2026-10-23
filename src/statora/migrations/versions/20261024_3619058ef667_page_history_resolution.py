"""page history resolution

Revision ID: 3619058ef667
Revises: dcff904c1d81
Create Date: 2026-10-24 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3619058ef667"
down_revision: str | None = "dcff904c1d81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "status_pages",
        sa.Column("history_resolution", sa.String(length=8), server_default="day", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("status_pages", "history_resolution")
