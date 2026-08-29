"""Chat orchestration — STUB (Phase 1, CLAUDE.md §11).

Flow: load_context -> graph.astream_events(v2) -> convert to SSE protocol ->
flush to client -> persist message -> publish SQS memory-consolidation job.
"""

from __future__ import annotations

from collections.abc import AsyncIterator


async def run_chat_stream(conversation_id: str, run_id: str, user_id: str) -> AsyncIterator[str]:
    """Yield SSE frames (see ``app.core.streaming``)."""
    raise NotImplementedError("Phase 1")
    yield  # pragma: no cover  (marks this an async generator)
