"""RAG agent — STUB (Phase 2, CLAUDE.md §10, §12).

Calls ``hybrid_retrieve`` then formats context into
``state['intermediate_results']['rag']``.
"""

from __future__ import annotations

from app.agents.supervisor.state import GenieState


async def rag_node(state: GenieState) -> GenieState:
    raise NotImplementedError("Phase 2")
