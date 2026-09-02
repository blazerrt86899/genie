"""conversations pinned + unread

Revision ID: f041f866790f
Revises: 344f477b87da
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f041f866790f"
down_revision: str | None = "344f477b87da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "genie"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("pinned", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema=_SCHEMA,
    )
    op.add_column(
        "conversations",
        sa.Column("unread", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("conversations", "unread", schema=_SCHEMA)
    op.drop_column("conversations", "pinned", schema=_SCHEMA)
