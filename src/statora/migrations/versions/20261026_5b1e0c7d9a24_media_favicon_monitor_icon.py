"""media uploads, status page favicon, monitor icon and link

Revision ID: 5b1e0c7d9a24
Revises: 3619058ef667
Create Date: 2026-10-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b1e0c7d9a24"
down_revision: str | None = "3619058ef667"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("sha256", name=op.f("uq_media_sha256")),
    )
    op.add_column("status_pages", sa.Column("favicon", sa.String(length=2048), nullable=True))
    op.add_column("monitors", sa.Column("icon", sa.String(length=2048), nullable=True))
    op.add_column("monitors", sa.Column("link_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("monitors", "link_url")
    op.drop_column("monitors", "icon")
    op.drop_column("status_pages", "favicon")
    op.drop_table("media")
