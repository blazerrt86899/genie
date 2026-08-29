"""Memory consolidation logic — STUB (Phase 2/3, CLAUDE.md §13).

Idempotent: guard on ``processed_at IS NULL`` before acting (CLAUDE.md §4.5).
"""

from __future__ import annotations


async def consolidate_conversation(conversation_id: str) -> None:
    raise NotImplementedError("Phase 2")
