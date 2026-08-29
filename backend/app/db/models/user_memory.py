"""UserMemory model — Phase 2 long-term memory (CLAUDE.md §8.4, §13).

STUB: not yet wired into Base.metadata / migrations.

Planned columns: id, user_id -> users.id, content, embedding vector(1536),
fts_content tsvector (trigger-populated), importance float, source_conversation_id,
created_at, updated_at.
Indexes: ivfflat(embedding), gin(fts_content).
"""

from __future__ import annotations

__all__: list[str] = []
