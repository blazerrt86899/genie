"""Web Search agent — STUB (Phase 1, CLAUDE.md §12).

Uses Tavily. Writes to ``state['intermediate_results']['web_search']``.
Single responsibility: search only — never creates tasks.
"""

from __future__ import annotations

from app.agents.supervisor.state import GenieState


async def web_search_node(state: GenieState) -> GenieState:
    raise NotImplementedError("Phase 1")
