"""Attachment model — a file the user attached to one chat message.

Text-only (`pdf` / `txt` / `md`); the extracted `content` is injected into that
one turn's prompts (CLAUDE.md §9). Conversation-scoped and ephemeral in intent —
distinct from Phase-2 `documents` (a project RAG knowledge base).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, TimestampMixin

ATTACHMENT_KINDS: frozenset[str] = frozenset({"pdf", "txt", "md"})


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL until the message it's attached to exists (a brand-new chat has no id
    # at upload time). Linked in chat_service.create_turn.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf | txt | md
    content: Mapped[str] = mapped_column(Text, nullable=False)  # extracted plain text
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
