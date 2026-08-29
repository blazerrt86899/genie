"""MessageRepository — STUB (Phase 1). All queries filter by user_id."""

from __future__ import annotations

from app.db.models.message import Message
from app.db.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message
