"""SQLAlchemy ORM models.

Import every ACTIVE model here so Alembic autogenerate + ``Base.metadata``
see them. Phase 2+ models live in their own files but are intentionally NOT
imported yet (and do not inherit ``Base``) so the first migration only creates
``users`` / ``conversations`` / ``messages``.
"""

from app.db.models.base import Base
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.user import User

__all__ = ["Base", "User", "Conversation", "Message"]
