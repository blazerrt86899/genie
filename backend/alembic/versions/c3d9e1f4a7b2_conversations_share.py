"""conversations share_token + shared_at

Revision ID: c3d9e1f4a7b2
Revises: f041f866790f
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d9e1f4a7b2"
down_revision: str | None = "f041f866790f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "genie"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("share_token", sa.String(length=24), nullable=True),
        schema=_SCHEMA,
    )
    op.add_column(
        "conversations",
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        schema=_SCHEMA,
    )
    op.create_unique_constraint(
        "uq_conversations_share_token",
        "conversations",
        ["share_token"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_conversations_share_token", "conversations", schema=_SCHEMA, type_="unique"
    )
    op.drop_column("conversations", "shared_at", schema=_SCHEMA)
    op.drop_column("conversations", "share_token", schema=_SCHEMA)
