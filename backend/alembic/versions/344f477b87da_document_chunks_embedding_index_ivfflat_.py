"""document_chunks embedding index: ivfflat → hnsw

ivfflat is an approximate index whose recall collapses on small tables — with a
few chunks spread across 100 lists a query probes ~1 list and returns almost
nothing, so per-project retrieval silently missed most matches. HNSW keeps high
recall at any size.

Revision ID: 344f477b87da
Revises: 883a87726339
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "344f477b87da"
down_revision: str | None = "883a87726339"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genie.ix_document_chunks_embedding")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON genie.document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genie.ix_document_chunks_embedding")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON genie.document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
