"""L1 memory — rate limiting (CLAUDE.md §13)."""

from __future__ import annotations

from app.memory.short_term import check_rate_limit


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> None:
        self.expires[key] = ttl


async def test_allows_up_to_the_limit_then_blocks():
    redis = FakeRedis()
    results = [await check_rate_limit(redis, "u1", 3) for _ in range(5)]
    assert results == [True, True, True, False, False]
    # TTL set exactly once (on the first hit of the window)
    assert len(redis.expires) == 1


async def test_users_are_isolated():
    redis = FakeRedis()
    assert await check_rate_limit(redis, "u1", 1) is True
    assert await check_rate_limit(redis, "u1", 1) is False
    assert await check_rate_limit(redis, "u2", 1) is True
