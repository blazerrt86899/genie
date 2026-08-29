"""ProjectRepository (CLAUDE.md §4.4). All queries filter by user_id."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select, update

from app.db.models.conversation import Conversation
from app.db.models.project import Project
from app.db.repositories.base import BaseRepository

_EDITABLE = {"name", "description", "instructions"}


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def create(
        self,
        user_id: uuid.UUID,
        name: str,
        description: str | None = None,
        instructions: str | None = None,
    ) -> Project:
        return await self.add(
            Project(
                user_id=user_id,
                name=name,
                description=description,
                instructions=instructions,
            )
        )

    async def get_for_user(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Project | None:
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id, Project.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Project, int]]:
        """Projects newest-updated first, each with its conversation count."""
        result = await self.db.execute(
            select(Project, func.count(Conversation.id))
            .outerjoin(Conversation, Conversation.project_id == Project.id)
            .where(Project.user_id == user_id)
            .group_by(Project.id)
            .order_by(Project.updated_at.desc())
        )
        return [(p, count) for p, count in result.all()]

    async def update(
        self, project_id: uuid.UUID, user_id: uuid.UUID, **fields: str | None
    ) -> Project | None:
        values = {k: v for k, v in fields.items() if k in _EDITABLE}
        if values:
            await self.db.execute(
                update(Project)
                .where(Project.id == project_id, Project.user_id == user_id)
                .values(**values)
            )
            await self.db.commit()
        return await self.get_for_user(project_id, user_id)

    async def delete_for_user(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        result = await self.db.execute(
            delete(Project).where(
                Project.id == project_id, Project.user_id == user_id
            )
        )
        await self.db.commit()
        return (getattr(result, "rowcount", 0) or 0) > 0
