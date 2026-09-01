"""Document model — a source in a project's Knowledge Base (CLAUDE.md §10, §15).

Uploaded to S3, then walked through the ingestion pipeline
(``upload → partition → chunk → vectorize → store``) by the ingestion worker.
The resulting text lives in ``document_chunks``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.project import Project

DOCUMENT_KINDS: frozenset[str] = frozenset({"pdf", "md", "txt"})
DOCUMENT_STATUSES: frozenset[str] = frozenset({"queued", "processing", "ready", "failed"})
# ordered pipeline phases (drives the transparency modal)
DOCUMENT_PHASES: tuple[str, ...] = (
    "upload",
    "partition",
    "chunk",
    "vectorize",
    "store",
    "done",
)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | md | txt
    s3_key: Mapped[str] = mapped_column(String(600), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    phase: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    error: Mapped[str | None] = mapped_column(Text)
    # {"elements": {"text": N, "tables": N, ...}, "chunk_count": N}
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(passive_deletes=True)
