"""Conversation model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.message import Message
    from app.db.models.project import Project
    from app.db.models.user import User


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    # The chat sidebar lists a user's conversations newest-activity first;
    # Postgres scans this btree backward for ORDER BY last_message_at DESC.
    __table_args__ = (Index("ix_conversations_user_recent", "user_id", "last_message_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    # Bumped on every message — the chat sidebar sorts by this (recency).
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Picked chat-model id (MODEL_CATALOG). NULL → the server default.
    model: Mapped[str | None] = mapped_column(String(40))
    # Sidebar: pinned chats sort to a section at the top; `unread` is a manual
    # flag (set from the ⋯ menu) that clears when the chat is opened.
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    user: Mapped[User] = relationship(back_populates="conversations")
    project: Mapped[Project | None] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        passive_deletes=True,
    )
