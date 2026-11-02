"""status page show_title (hide the page name under a logo)

Revision ID: 6a1f3c8e2b47
Revises: 4d2e9b7a1c03
Create Date: 2026-11-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6a1f3c8e2b47"
down_revision: str | None = "4d2e9b7a1c03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "status_pages", sa.Column("show_title", sa.Boolean(), server_default=sa.true(), nullable=False)
    )


def downgrade() -> None:
    op.drop_column("status_pages", "show_title")
