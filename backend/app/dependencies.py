"""FastAPI dependency injection surface (CLAUDE.md §5).

Import dependencies from here in endpoint modules so the wiring has one home.
"""

from __future__ import annotations

from app.core.clerk import get_current_user
from app.core.redis import get_redis
from app.db.session import get_db

__all__ = ["get_db", "get_redis", "get_current_user"]
