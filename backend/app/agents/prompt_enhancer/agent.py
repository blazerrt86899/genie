"""Prompt Enhancer agent — STUB (Phase 1, CLAUDE.md §12).

Runs first, always. Populates ``state['intent']`` + an enhanced query.
"""

from __future__ import annotations

from app.agents.supervisor.state import GenieState


async def prompt_enhancer_node(state: GenieState) -> GenieState:
    raise NotImplementedError("Phase 1")
