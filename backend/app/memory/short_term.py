"""L1 memory — Redis (CLAUDE.md §13). STUB (Phase 1).

    recent_messages:{user_id}   LPUSH/LTRIM last 10, TTL 2h
    rate_limit:{user_id}:{min}  INCR/EXPIRE, TTL 1 min
"""

from __future__ import annotations


async def get_recent_messages(user_id: str, limit: int = 10) -> list[dict]:
    raise NotImplementedError("Phase 1")


async def push_recent_message(user_id: str, message: dict) -> None:
    raise NotImplementedError("Phase 1")


async def check_rate_limit(user_id: str, limit_per_minute: int) -> bool:
    """Return True if the request is allowed."""
    raise NotImplementedError("Phase 1")
