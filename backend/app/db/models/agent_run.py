"""AgentRun model — LangGraph run observability (CLAUDE.md §8.2).

STUB: not yet wired into Base.metadata / migrations.

Planned columns: id, user_id -> users.id, conversation_id -> conversations.id,
run_id, agents_invoked jsonb, token_usage jsonb, status, error, started_at,
finished_at.
"""

from __future__ import annotations

__all__: list[str] = []
