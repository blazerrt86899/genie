"""OAuthCredential model — Phase 3 Google Calendar tokens (CLAUDE.md §15).

STUB: not yet wired into Base.metadata / migrations.
Tokens MUST be Fernet-encrypted before insert (CLAUDE.md §18).

Planned columns: id, user_id -> users.id, provider (google), access_token_enc,
refresh_token_enc, scope, expires_at, created_at, updated_at.
"""

from __future__ import annotations

__all__: list[str] = []
