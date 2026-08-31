"""TaskRepository (CLAUDE.md §4.4). Every query filters by ``user_id``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models.task import Task
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def create(
        self,
        user_id: uuid.UUID,
        title: str,
        *,
        description: str | None = None,
        conversation_id: uuid.UUID | None = None,
        source_agent: str | None = None,
    ) -> Task:
        def _row(conv: uuid.UUID | None) -> Task:
            return Task(
                user_id=user_id,
                title=title,
                description=description,
                conversation_id=conv,
                source_agent=source_agent,
                status="todo",
            )

        try:
            task = await self.add(_row(conversation_id))
        except IntegrityError:
            # A stale / unknown conversation_id must not block the task.
            await self.db.rollback()
            logger.warning(
                "task_create_conversation_link_dropped",
                user_id=str(user_id),
                conversation_id=str(conversation_id) if conversation_id else None,
            )
            task = await self.add(_row(None))
        logger.info(
            "task_created",
            task_id=str(task.id),
            user_id=str(user_id),
            conversation_id=str(conversation_id) if conversation_id else None,
            source_agent=source_agent,
        )
        return task

    async def get_for_user(self, task_id: uuid.UUID, user_id: uuid.UUID) -> Task | None:
        result = await self.db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID, *, include_archived: bool = False
    ) -> list[Task]:
        stmt = select(Task).where(Task.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(Task.status != "archived")
        stmt = stmt.order_by(Task.created_at.desc())
        rows = list((await self.db.execute(stmt)).scalars().all())
        logger.debug(
            "tasks_listed", user_id=str(user_id), count=len(rows), include_archived=include_archived
        )
        return rows

    async def find_by_title(self, user_id: uuid.UUID, query: str) -> Task | None:
        """Best fuzzy match for 'move the report task' — non-archived first, newest."""
        like = f"%{query.strip()}%"
        stmt = (
            select(Task)
            .where(Task.user_id == user_id, Task.title.ilike(like))
            .order_by((Task.status == "archived"), Task.created_at.desc())
            .limit(1)
        )
        match = (await self.db.execute(stmt)).scalar_one_or_none()
        logger.info(
            "task_find_by_title", user_id=str(user_id), query=query, matched=match is not None
        )
        return match

    async def set_status(
        self, task_id: uuid.UUID, user_id: uuid.UUID, status: str
    ) -> Task | None:
        archived_at = datetime.now(UTC) if status == "archived" else None
        await self.db.execute(
            update(Task)
            .where(Task.id == task_id, Task.user_id == user_id)
            .values(status=status, archived_at=archived_at)
        )
        await self.db.commit()
        task = await self.get_for_user(task_id, user_id)
        logger.info(
            "task_status_changed",
            task_id=str(task_id),
            user_id=str(user_id),
            status=status,
            found=task is not None,
        )
        return task

    async def update(
        self, task_id: uuid.UUID, user_id: uuid.UUID, **fields: str | None
    ) -> Task | None:
        values = {k: v for k, v in fields.items() if k in {"title", "description"}}
        if values:
            await self.db.execute(
                update(Task)
                .where(Task.id == task_id, Task.user_id == user_id)
                .values(**values)
            )
            await self.db.commit()
            logger.info(
                "task_updated_details",
                task_id=str(task_id),
                user_id=str(user_id),
                fields=sorted(values.keys()),
            )
        return await self.get_for_user(task_id, user_id)

    async def archive_done(self, user_id: uuid.UUID) -> int:
        result = await self.db.execute(
            update(Task)
            .where(Task.user_id == user_id, Task.status == "done")
            .values(status="archived", archived_at=func.now())
        )
        await self.db.commit()
        count = getattr(result, "rowcount", 0) or 0
        logger.info("tasks_archive_done", user_id=str(user_id), archived=count)
        return count

    async def delete_for_user(self, task_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            delete(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        await self.db.commit()
        deleted = (getattr(result, "rowcount", 0) or 0) > 0
        logger.info(
            "task_deleted", task_id=str(task_id), user_id=str(user_id), deleted=deleted
        )
        return deleted
