"""UserRepository — includes Clerk sync helpers (CLAUDE.md §7.5).

`create_from_clerk_token` is the auto-provision path used by `get_current_user`
the first time a Clerk user hits the API. The `*_from_clerk` variants are driven
by the `POST /webhooks/clerk` handler.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core import clerk_api
from app.db.models.user import User
from app.db.repositories.base import BaseRepository

_PLACEHOLDER_EMAIL = "{clerk_id}@users.noreply.clerk"


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_clerk_id(self, clerk_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.clerk_id == clerk_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    # ─── Auto-provision from a verified session token ──────────────────────
    async def create_from_clerk_token(self, jwt_payload: dict) -> User:
        clerk_id: str = jwt_payload["sub"]
        profile = await clerk_api.fetch_clerk_user(clerk_id)

        if profile:
            email = clerk_api.primary_email(profile) or _PLACEHOLDER_EMAIL.format(clerk_id=clerk_id)
            user = User(
                clerk_id=clerk_id,
                email=email,
                full_name=clerk_api.full_name(profile),
                avatar_url=clerk_api.avatar_url(profile),
                email_verified=clerk_api.email_verified(profile),
            )
        else:
            user = User(
                clerk_id=clerk_id,
                email=jwt_payload.get("email") or _PLACEHOLDER_EMAIL.format(clerk_id=clerk_id),
                full_name=jwt_payload.get("name"),
                email_verified=bool(jwt_payload.get("email_verified")),
            )

        self.db.add(user)
        try:
            await self.db.commit()
        except IntegrityError:
            # Concurrent provision for the same clerk_id — take the winner's row.
            await self.db.rollback()
            existing = await self.get_by_clerk_id(clerk_id)
            if existing is None:
                raise
            return existing
        await self.db.refresh(user)
        return user

    # ─── Webhook-driven sync (CLAUDE.md §7.4) ──────────────────────────────
    async def create_from_clerk(self, clerk_data: dict) -> User:
        clerk_id: str = clerk_data["id"]
        existing = await self.get_by_clerk_id(clerk_id)
        if existing is not None:
            await self.update_from_clerk(clerk_data)
            return existing
        user = User(
            clerk_id=clerk_id,
            email=clerk_api.primary_email(clerk_data)
            or _PLACEHOLDER_EMAIL.format(clerk_id=clerk_id),
            full_name=clerk_api.full_name(clerk_data),
            avatar_url=clerk_api.avatar_url(clerk_data),
            email_verified=clerk_api.email_verified(clerk_data),
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_from_clerk(self, clerk_data: dict) -> None:
        await self.db.execute(
            update(User)
            .where(User.clerk_id == clerk_data["id"])
            .values(
                email=clerk_api.primary_email(clerk_data),
                full_name=clerk_api.full_name(clerk_data),
                avatar_url=clerk_api.avatar_url(clerk_data),
                email_verified=clerk_api.email_verified(clerk_data),
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

    async def soft_delete_by_clerk_id(self, clerk_id: str) -> None:
        """Preserve conversation history — just detach the Clerk identity."""
        await self.db.execute(
            update(User)
            .where(User.clerk_id == clerk_id)
            .values(
                clerk_id=f"deleted_{clerk_id}",
                email=f"deleted_{clerk_id}@deleted.invalid",
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

    async def touch_last_active(self, user_id: uuid.UUID) -> None:
        try:
            await self.db.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_active_at=datetime.now(UTC))
            )
            await self.db.commit()
        except Exception:  # noqa: BLE001  — best-effort, never blocks a request
            await self.db.rollback()
