"""SSE event helpers — the streaming protocol (CLAUDE.md §11).

Frontend parses events by their ``type`` field. Keep this in sync with
``frontend/src/lib/sse.ts``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

SSEEventType = Literal[
    "agent_start",
    "token",
    "agent_end",
    "plan",
    "message_break",
    "message_agents",
    "sources",
    "guardrail",
    "task_created",
    "task_updated",
    "tasks_archived",
    "title",
    "interrupt",
    "error",
    "done",
]


def format_sse_event(event_type: SSEEventType, **data: Any) -> str:
    """Serialize a single SSE ``data:`` frame (newline-terminated)."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, default=str)}\n\n"


def sse_done(total_tokens: int, run_id: str, **extra: Any) -> str:
    clean = {k: v for k, v in extra.items() if v is not None}
    return format_sse_event("done", total_tokens=total_tokens, run_id=run_id, **clean)


def sse_error(message: str, code: str = "internal_error") -> str:
    return format_sse_event("error", message=message, code=code)
