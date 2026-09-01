"""L1 memory — Redis (CLAUDE.md §13).

`check_rate_limit` is live (Phase 1). `recent_messages` (cross-conversation
recent activity) is **Phase 6** — the LangGraph checkpointer already gives
per-conversation memory.

    rate_limit:{user_id}:{minute}  INCR/EXPIRE, TTL ~65s
    recent_messages:{user_id}      LPUSH/LTRIM last 10, TTL 2h   (Phase 6)
"""

from __future__ import annotations

import time

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_RATE_KEY = "rate_limit:{user_id}:{minute}"
_RATE_TTL_SECONDS = 65


async def check_rate_limit(redis: Redis, user_id: str, limit_per_minute: int) -> bool:
    """Fixed-window counter. Returns True if the request is allowed."""
    minute = int(time.time() // 60)
    key = _RATE_KEY.format(user_id=user_id, minute=minute)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, _RATE_TTL_SECONDS)
    allowed = count <= limit_per_minute
    if not allowed:
        logger.warning(
            "rate_limit_exceeded", user_id=user_id, count=count, limit=limit_per_minute
        )
    return allowed


# ─── Phase 6 ─────────────────────────────────────────────────────────────────


async def get_recent_messages(user_id: str, limit: int = 10) -> list[dict]:
    raise NotImplementedError("Phase 6 — see CLAUDE.md §15")


async def push_recent_message(user_id: str, message: dict) -> None:
    raise NotImplementedError("Phase 6 — see CLAUDE.md §15")
