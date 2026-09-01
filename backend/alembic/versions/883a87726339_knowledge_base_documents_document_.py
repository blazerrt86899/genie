"""knowledge base — documents, document_chunks, projects.rag_settings

Revision ID: 883a87726339
Revises: 0b4ae74dbb70
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "883a87726339"
down_revision: str | None = "0b4ae74dbb70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "genie"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "projects",
        sa.Column(
            "rag_settings",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        schema=_SCHEMA,
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("s3_key", sa.String(length=600), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "stats", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["genie.projects.id"], name="fk_documents_project_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["genie.users.id"], name="fk_documents_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=_SCHEMA,
    )
    op.create_index(op.f("ix_genie_documents_project_id"), "documents", ["project_id"], schema=_SCHEMA)
    op.create_index(op.f("ix_genie_documents_user_id"), "documents", ["user_id"], schema=_SCHEMA)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.Column("fts_content", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["genie.documents.id"],
            name="fk_document_chunks_document_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["genie.projects.id"],
            name="fk_document_chunks_project_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["genie.users.id"],
            name="fk_document_chunks_user_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=_SCHEMA,
    )
    op.create_index(
        op.f("ix_genie_document_chunks_document_id"), "document_chunks", ["document_id"], schema=_SCHEMA
    )
    op.create_index(
        op.f("ix_genie_document_chunks_project_id"), "document_chunks", ["project_id"], schema=_SCHEMA
    )

    # ── raw: pgvector + FTS index + the trigger that fills fts_content ──────
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON genie.document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_fts ON genie.document_chunks USING gin (fts_content)"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION genie.update_fts_content() RETURNS trigger AS $$
        BEGIN
          NEW.fts_content := to_tsvector('english', COALESCE(NEW.content, ''));
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER update_document_chunks_fts BEFORE INSERT OR UPDATE OF content "
        "ON genie.document_chunks FOR EACH ROW EXECUTE FUNCTION genie.update_fts_content()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS update_document_chunks_fts ON genie.document_chunks")
    op.drop_table("document_chunks", schema=_SCHEMA)
    op.drop_table("documents", schema=_SCHEMA)
    op.drop_column("projects", "rag_settings", schema=_SCHEMA)
