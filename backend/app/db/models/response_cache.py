"""ResponseCache model — the semantic answer cache (CLAUDE.md § caching).

One row per cached answer to a tool-free, context-free question. A new question
whose embedding is within `RESPONSE_CACHE_SIMILARITY` cosine of a live row
(younger than `RESPONSE_CACHE_TTL_HOURS`) is served straight from here, skipping
the whole graph.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin

EMBEDDING_DIM = 1536


class ResponseCache(Base, TimestampMixin):
    __tablename__ = "response_cache"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_norm: Mapped[str] = mapped_column(Text, nullable=False)
    query_embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
