"""Repository pattern base (CLAUDE.md §4.4).

No raw SQL or Supabase client calls in route handlers — all DB access flows
through repositories. Every user-data query MUST filter by ``user_id``
(CLAUDE.md §4.7).
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import Base

logger = structlog.get_logger("app.db.repo")

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_: uuid.UUID) -> ModelT | None:
        obj = await self.db.get(self.model, id_)
        logger.debug(
            "db_get_by_id", table=self.model.__tablename__, id=str(id_), found=obj is not None
        )
        return obj

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        result = await self.db.execute(select(self.model).limit(limit).offset(offset))
        rows = list(result.scalars().all())
        logger.debug("db_list_all", table=self.model.__tablename__, count=len(rows))
        return rows

    async def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        logger.info(
            "db_insert", table=self.model.__tablename__, id=str(getattr(obj, "id", None))
        )
        return obj
