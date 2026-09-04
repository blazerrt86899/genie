"""GeneratedFileRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select, update

from app.db.models.generated_file import GeneratedFile
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class GeneratedFileRepository(BaseRepository[GeneratedFile]):
    model = GeneratedFile

    async def get_for_user(
        self, file_id: uuid.UUID, user_id: uuid.UUID
    ) -> GeneratedFile | None:
        result = await self.db.execute(
            select(GeneratedFile).where(
                GeneratedFile.id == file_id, GeneratedFile.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def link_message(self, file_id: uuid.UUID, message_id: uuid.UUID) -> None:
        await self.db.execute(
            update(GeneratedFile)
            .where(GeneratedFile.id == file_id)
            .values(message_id=message_id)
        )
        await self.db.commit()
        logger.info(
            "generated_file_linked", file_id=str(file_id), message_id=str(message_id)
        )

    async def list_for_conversation(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[GeneratedFile]:
        result = await self.db.execute(
            select(GeneratedFile)
            .where(
                GeneratedFile.conversation_id == conversation_id,
                GeneratedFile.user_id == user_id,
            )
            .order_by(GeneratedFile.created_at)
        )
        return list(result.scalars().all())
