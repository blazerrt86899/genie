"""L2 memory — Supabase ``user_memory`` hybrid search (CLAUDE.md §13). STUB (Phase 2)."""

from __future__ import annotations


async def hybrid_search_memories(query: str, user_id: str, match_count: int = 5) -> list[dict]:
    """Calls the ``hybrid_search_memories`` Supabase RPC. Filters by user_id."""
    raise NotImplementedError("Phase 2")
