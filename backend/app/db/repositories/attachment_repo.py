"""AttachmentRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, select, update

from app.db.models.attachment import Attachment
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class AttachmentRepository(BaseRepository[Attachment]):
    model = Attachment

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        filename: str,
        kind: str,
        content: str,
        char_count: int,
        token_estimate: int,
    ) -> Attachment:
        att = await self.add(
            Attachment(
                user_id=user_id,
                filename=filename,
                kind=kind,
                content=content,
                char_count=char_count,
                token_estimate=token_estimate,
            )
        )
        logger.info(
            "attachment_created",
            attachment_id=str(att.id),
            user_id=str(user_id),
            kind=kind,
            char_count=char_count,
        )
        return att

    async def get_for_user(
        self, attachment_id: uuid.UUID, user_id: uuid.UUID
    ) -> Attachment | None:
        result = await self.db.execute(
            select(Attachment).where(
                Attachment.id == attachment_id, Attachment.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user_ids(
        self, user_id: uuid.UUID, ids: list[uuid.UUID]
    ) -> list[Attachment]:
        if not ids:
            return []
        result = await self.db.execute(
            select(Attachment).where(
                Attachment.user_id == user_id, Attachment.id.in_(ids)
            )
        )
        return list(result.scalars().all())

    async def link(
        self,
        user_id: uuid.UUID,
        ids: list[uuid.UUID],
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> None:
        if not ids:
            return
        await self.db.execute(
            update(Attachment)
            .where(Attachment.user_id == user_id, Attachment.id.in_(ids))
            .values(conversation_id=conversation_id, message_id=message_id)
        )
        await self.db.commit()
        logger.info(
            "attachment_link",
            user_id=str(user_id),
            count=len(ids),
            conversation_id=str(conversation_id),
            message_id=str(message_id),
        )

    async def delete_for_user(
        self, attachment_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            delete(Attachment).where(
                Attachment.id == attachment_id, Attachment.user_id == user_id
            )
        )
        await self.db.commit()
        deleted = (getattr(result, "rowcount", 0) or 0) > 0
        logger.info(
            "attachment_deleted",
            attachment_id=str(attachment_id),
            user_id=str(user_id),
            deleted=deleted,
        )
        return deleted
