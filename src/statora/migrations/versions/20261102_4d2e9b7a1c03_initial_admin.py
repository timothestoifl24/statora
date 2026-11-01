"""initial admin (created in the first-run setup, protected from deletion)

Revision ID: 4d2e9b7a1c03
Revises: 8c3f2a1d7e55
Create Date: 2026-11-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d2e9b7a1c03"
down_revision: str | None = "8c3f2a1d7e55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_initial_admin", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    # Existing instances were set up with `statora create-admin`: the oldest local admin becomes
    # the initial admin, so `statora reset-admin` keeps working for them.
    op.execute(
        "UPDATE users SET is_initial_admin = true WHERE id = ("
        "SELECT min(id) FROM users WHERE role = 'admin' AND auth_provider_id IS NULL)"
    )
    op.create_index(
        "uq_users_initial_admin",
        "users",
        ["is_initial_admin"],
        unique=True,
        postgresql_where=sa.text("is_initial_admin"),
        sqlite_where=sa.text("is_initial_admin"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_initial_admin", table_name="users")
    op.drop_column("users", "is_initial_admin")
