"""Task Creator agent — STUB (Phase 2, CLAUDE.md §12).

``with_structured_output(ExtractedTask)`` -> persist via TaskRepository -> emit
SSE ``task_created`` event. Single responsibility: never searches the web.
"""

from __future__ import annotations

from app.agents.supervisor.state import GenieState


async def task_creator_node(state: GenieState) -> GenieState:
    raise NotImplementedError("Phase 2")
