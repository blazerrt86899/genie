"""Calendar agent — STUB (Phase 3, CLAUDE.md §12).

Reads events freely; writes go through ``interrupt_before=["calendar"]`` so the
user must confirm (CLAUDE.md §18).
"""

from __future__ import annotations

from app.agents.supervisor.state import GenieState


async def calendar_node(state: GenieState) -> GenieState:
    raise NotImplementedError("Phase 3")
