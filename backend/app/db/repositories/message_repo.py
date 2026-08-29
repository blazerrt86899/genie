"""MessageRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.message import Message
from app.db.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        content: str,
    ) -> Message:
        return await self.add(
            Message(
                conversation_id=conversation_id,
                user_id=user_id,
                role=role,
                content=content,
            )
        )

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, limit: int = 200
    ) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
