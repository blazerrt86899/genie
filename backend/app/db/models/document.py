"""Document model — Phase 2 (CLAUDE.md §15).

STUB: not yet wired into Base.metadata / migrations.

Planned columns: id, user_id -> users.id, filename, s3_key, content_type,
status (pending|processing|ready|failed), processed_at, created_at, updated_at.
"""

from __future__ import annotations

__all__: list[str] = []
