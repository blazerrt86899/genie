"""DocumentRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select, update

from app.db.models.document import Document
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def create(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        filename: str,
        kind: str,
        s3_key: str,
        byte_size: int,
    ) -> Document:
        doc = await self.add(
            Document(
                user_id=user_id,
                project_id=project_id,
                filename=filename,
                kind=kind,
                s3_key=s3_key,
                byte_size=byte_size,
                status="queued",
                phase="upload",
            )
        )
        logger.info(
            "document_created",
            document_id=str(doc.id),
            project_id=str(project_id),
            kind=kind,
            byte_size=byte_size,
        )
        return doc

    async def get_for_user(
        self, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> Document | None:
        result = await self.db.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get(self, document_id: uuid.UUID) -> Document | None:
        """No user filter — for the ingestion worker (its own session)."""
        return await self.db.get(Document, document_id)

    async def list_for_project(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.project_id == project_id, Document.user_id == user_id)
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def count_ready_for_project(self, project_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.project_id == project_id, Document.status == "ready")
        )
        return int(result.scalar_one())

    async def count_for_project(self, project_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(Document).where(Document.project_id == project_id)
        )
        return int(result.scalar_one())

    async def set_phase(
        self,
        document_id: uuid.UUID,
        phase: str,
        *,
        status: str = "processing",
        stats_merge: dict | None = None,
        error: str | None = None,
    ) -> None:
        values: dict = {"phase": phase, "status": status}
        if error is not None:
            values["error"] = error
        if stats_merge:
            values["stats"] = Document.stats.op("||")(stats_merge)
        await self.db.execute(update(Document).where(Document.id == document_id).values(**values))
        await self.db.commit()
        logger.info("document_phase", document_id=str(document_id), phase=phase, status=status)

    async def mark_ready(self, document_id: uuid.UUID, stats_merge: dict) -> None:
        await self.db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status="ready",
                phase="done",
                error=None,
                processed_at=datetime.now(UTC),
                stats=Document.stats.op("||")(stats_merge),
            )
        )
        await self.db.commit()
        logger.info("document_ready", document_id=str(document_id))

    async def delete_for_user(
        self, document_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        doc = await self.get_for_user(document_id, user_id)
        if doc is None:
            return False
        await self.db.delete(doc)  # cascades to document_chunks
        await self.db.commit()
        logger.info("document_deleted", document_id=str(document_id))
        return True
