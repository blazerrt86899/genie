"""ConversationRepository — STUB (Phase 1). All queries filter by user_id."""

from __future__ import annotations

from app.db.models.conversation import Conversation
from app.db.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation
