"""Async Redis client singleton (CLAUDE.md §13).

Keys used across the app:
    recent_messages:{user_id}     list, TTL 2h
    rate_limit:{user_id}:{minute} counter, TTL 1m
    clerk:jwks                    JWKS JSON, TTL JWKS_CACHE_TTL_SECONDS
    user_by_clerk:{clerk_id}      internal user UUID, TTL CLERK_USER_CACHE_TTL_SECONDS
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.config import settings

_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return the process-wide Redis client (lazy, connection-pooled)."""
    global _client
    if _client is None:
        _client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def get_redis() -> Redis:
    """FastAPI dependency."""
    return get_redis_client()


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
