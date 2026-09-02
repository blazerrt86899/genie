"""response_cache — semantic answer cache (pgvector)

Revision ID: b8e2f4a1c9d3
Revises: c3d9e1f4a7b2
Create Date: 2026-09-02
"""
from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "b8e2f4a1c9d3"
down_revision: str | None = "c3d9e1f4a7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "genie"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "response_cache",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("query_norm", sa.Text(), nullable=False),
        sa.Column("query_embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["genie.users.id"], name="fk_response_cache_user", ondelete="CASCADE"
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        op.f("ix_genie_response_cache_user_id"), "response_cache", ["user_id"], schema=_SCHEMA
    )
    op.create_index(
        "ix_response_cache_user_created",
        "response_cache",
        ["user_id", "created_at"],
        schema=_SCHEMA,
    )
    op.execute(
        "CREATE INDEX ix_response_cache_embedding ON genie.response_cache "
        "USING hnsw (query_embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genie.ix_response_cache_embedding")
    op.drop_table("response_cache", schema=_SCHEMA)
