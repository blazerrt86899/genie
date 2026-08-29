"""DocumentChunk model — Phase 2 RAG store (CLAUDE.md §8.3, §10).

STUB: not yet wired into Base.metadata / migrations.

Planned columns: id, document_id -> documents.id, user_id -> users.id, content,
embedding vector(1536), fts_content tsvector (trigger-populated), metadata jsonb,
chunk_index, created_at.
Indexes: ivfflat(embedding), gin(fts_content), (document_id, user_id).
"""

from __future__ import annotations

__all__: list[str] = []
