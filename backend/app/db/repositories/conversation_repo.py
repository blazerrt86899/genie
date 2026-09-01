"""ConversationRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, func, select, update

from app.db.models.conversation import Conversation
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def create(
        self,
        user_id: uuid.UUID,
        title: str | None = None,
        project_id: uuid.UUID | None = None,
        model: str | None = None,
    ) -> Conversation:
        conv = await self.add(
            Conversation(user_id=user_id, title=title, project_id=project_id, model=model)
        )
        logger.info(
            "conversation_created",
            conversation_id=str(conv.id),
            user_id=str(user_id),
            project_id=str(project_id) if project_id else None,
            model=model,
        )
        return conv

    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(
                Conversation.last_message_at.desc().nulls_last(),
                Conversation.created_at.desc(),
            )
            .limit(limit)
        )
        rows = list(result.scalars().all())
        logger.debug("conversations_listed", user_id=str(user_id), count=len(rows))
        return rows

    async def list_for_project(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(
                Conversation.project_id == project_id,
                Conversation.user_id == user_id,
            )
            .order_by(
                Conversation.last_message_at.desc().nulls_last(),
                Conversation.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def touch(self, conversation_id: uuid.UUID) -> None:
        """Bump ``last_message_at`` — called on every new message."""
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(last_message_at=func.now())
        )
        await self.db.commit()

    async def set_title(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> None:
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .values(title=title)
        )
        await self.db.commit()
        logger.info(
            "conversation_titled", conversation_id=str(conversation_id), title=title
        )

    async def set_model(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID, model: str | None
    ) -> None:
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .values(model=model)
        )
        await self.db.commit()
        logger.info(
            "conversation_model_set", conversation_id=str(conversation_id), model=model
        )

    async def delete_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        await self.db.commit()
        deleted = (getattr(result, "rowcount", 0) or 0) > 0
        logger.info(
            "conversation_deleted",
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            deleted=deleted,
        )
        return deleted
