"""Repository pattern base (CLAUDE.md §4.4).

No raw SQL or Supabase client calls in route handlers — all DB access flows
through repositories. Every user-data query MUST filter by ``user_id``
(CLAUDE.md §4.7).
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id_: uuid.UUID) -> ModelT | None:
        return await self.db.get(self.model, id_)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        result = await self.db.execute(select(self.model).limit(limit).offset(offset))
        return list(result.scalars().all())

    async def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj
