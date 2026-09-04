"""GeneratedFile model — a downloadable file the ``file_creator`` agent made
(CLAUDE.md §12, §14).

Distinct from both `attachments` (a user-uploaded file, text extracted into one
turn's prompt) and `documents` (a project Knowledge Base source, chunked +
embedded for RAG) — this is Genie's own output: a Word/PDF/Excel/text/code file
written this turn, stored in S3, and offered back to the user as a download.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin

GENERATED_FILE_FORMATS: frozenset[str] = frozenset(
    {"md", "txt", "csv", "json", "docx", "pdf", "xlsx", "code"}
)


class GeneratedFile(Base, TimestampMixin):
    __tablename__ = "generated_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL until the assistant message it's attached to is persisted (the
    # message doesn't exist yet when the agent runs) — linked in chat_service.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    # md | txt | csv | json | docx | pdf | xlsx | code
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(600), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str | None] = mapped_column(Text)  # one-line blurb for the download card
