"""Task model — Phase 2 (CLAUDE.md §15).

STUB: not yet wired into Base.metadata / migrations. When Phase 2 starts,
make this inherit ``Base``, add it to ``models/__init__.py``, and generate a
migration.

Planned columns: id, user_id -> users.id, conversation_id -> conversations.id,
title, description, status (todo|in_progress|done), due_date, source_agent,
created_at, updated_at.
"""

from __future__ import annotations

__all__: list[str] = []
