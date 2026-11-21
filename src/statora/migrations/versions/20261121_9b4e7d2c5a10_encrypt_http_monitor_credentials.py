"""encrypt HTTP monitor request headers and body

Revision ID: 9b4e7d2c5a10
Revises: 6a1f3c8e2b47
Create Date: 2026-11-21 12:00:00.000000

HTTP monitors often carry credentials in their request headers or body. New and edited monitors
store them encrypted with STATORA_SECRET_KEY; this encrypts the values saved before that.
"""

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from statora.auth import crypto

revision: str = "9b4e7d2c5a10"
down_revision: str | None = "6a1f3c8e2b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


monitors = sa.table(
    "monitors",
    sa.column("id", sa.Integer),
    sa.column("type", sa.String),
    sa.column("config", sa.JSON().with_variant(JSONB(), "postgresql")),
)


def _convert(fn: Callable[[str], str]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.select(monitors.c.id, monitors.c.config).where(monitors.c.type == "http")).all()
    for monitor_id, config in rows:
        config = dict(config or {})
        changed = dict(config)
        headers = config.get("headers")
        if isinstance(headers, dict):
            changed["headers"] = {k: fn(v) if isinstance(v, str) else v for k, v in headers.items()}
        if isinstance(config.get("body"), str) and config["body"]:
            changed["body"] = fn(config["body"])
        if changed != config:
            bind.execute(monitors.update().where(monitors.c.id == monitor_id).values(config=changed))


def upgrade() -> None:
    # Nothing was encrypted before this revision: a value starting with "enc:" is plain text too.
    _convert(crypto.encrypt)


def downgrade() -> None:
    _convert(crypto.decrypt)
