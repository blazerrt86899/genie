"""DocumentChunkRepository — the project RAG store (CLAUDE.md §8.3, §10)."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, func, insert, select

from app.db.models.document_chunk import DocumentChunk
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    model = DocumentChunk

    async def bulk_insert(self, rows: list[dict]) -> int:
        """`rows` = [{document_id, project_id, user_id, chunk_index, content,
        token_count, embedding, metadata}]. The FTS trigger fills `fts_content`."""
        if not rows:
            return 0
        await self.db.execute(insert(DocumentChunk), rows)
        await self.db.commit()
        logger.info("document_chunks_inserted", count=len(rows))
        return len(rows)

    async def list_for_document(
        self, document_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[DocumentChunk]:
        result = await self.db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.user_id == user_id)
            .order_by(DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        return int(result.scalar_one())

    async def delete_for_document(self, document_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self.db.commit()
