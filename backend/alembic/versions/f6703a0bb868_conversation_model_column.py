"""conversation model column

Revision ID: f6703a0bb868
Revises: bed5223f2a47
Create Date: 2026-09-01 14:51:22.517441
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f6703a0bb868'
down_revision: str | None = 'bed5223f2a47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("model", sa.String(length=40), nullable=True),
        schema="genie",
    )


def downgrade() -> None:
    op.drop_column("conversations", "model", schema="genie")
