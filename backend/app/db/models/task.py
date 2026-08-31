"""Task model — the Kanban board (CLAUDE.md §12, §14).

Statuses: ``todo`` → ``in_progress`` → ``done`` → ``archived``. ``archived`` tasks
stay in the DB (for reporting) but drop off the board. Each task optionally links
to the ``conversations`` row it was created / discussed in (``SET NULL`` on
conversation delete — the task survives).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.user import User

TASK_STATUSES: frozenset[str] = frozenset({"todo", "in_progress", "done", "archived"})
BOARD_STATUSES: tuple[str, ...] = ("todo", "in_progress", "done")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    __table_args__ = (Index("ix_tasks_user_status", "user_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo")
    source_agent: Mapped[str | None] = mapped_column(String(50))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="tasks")
    conversation: Mapped[Conversation | None] = relationship(passive_deletes=True)
