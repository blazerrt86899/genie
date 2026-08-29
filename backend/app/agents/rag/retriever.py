"""RAG retriever — STUB (Phase 2, CLAUDE.md §10).

ALWAYS hybrid search (RRF) — never pure vector or pure FTS. ALWAYS filters by
``user_id`` (CLAUDE.md §4.7).
"""

from __future__ import annotations


async def hybrid_retrieve(query: str, user_id: str, match_count: int = 10) -> list[dict]:
    """Embed the query, call the ``hybrid_search_documents`` Supabase RPC."""
    raise NotImplementedError("Phase 2")
