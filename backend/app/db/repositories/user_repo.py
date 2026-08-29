"""UserRepository — includes Clerk sync helpers (CLAUDE.md §7.5).

Real implementations land in Phase 1. Signatures are fixed now so callers
(webhook handler, ``get_current_user``) can be written against them.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.user import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_clerk_id(self, clerk_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.clerk_id == clerk_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    # ─── Clerk webhook helpers (Phase 1) ───────────────────────────────────
    async def create_from_clerk(self, clerk_data: dict) -> User:
        """Called by webhook on ``user.created``."""
        raise NotImplementedError("Phase 1")

    async def create_from_clerk_token(self, jwt_payload: dict) -> User:
        """Fallback when ``get_current_user`` runs before the webhook arrives."""
        raise NotImplementedError("Phase 1")

    async def update_from_clerk(self, clerk_data: dict) -> None:
        """Called by webhook on ``user.updated``."""
        raise NotImplementedError("Phase 1")

    async def soft_delete_by_clerk_id(self, clerk_id: str) -> None:
        """Called by webhook on ``user.deleted`` — preserves conversation history."""
        raise NotImplementedError("Phase 1")

    async def touch_last_active(self, user_id: uuid.UUID) -> None:
        """Fire-and-forget ``last_active_at`` bump."""
        raise NotImplementedError("Phase 1")
