"""services/cache_service.py — the semantic response cache."""

from __future__ import annotations

import uuid

import pytest
from app.services import cache_service


def test_is_cacheable_query():
    assert cache_service.is_cacheable_query("explain the difference between a process and a thread")
    assert not cache_service.is_cacheable_query("hi")  # too short
    assert not cache_service.is_cacheable_query("what is the latest news on AI")  # time word
    assert not cache_service.is_cacheable_query("weather in Paris today")
    assert not cache_service.is_cacheable_query("stock price of AAPL right now")
    assert not cache_service.is_cacheable_query("the score of yesterday's match")


class FakeResult:
    def __init__(self, row=None):
        self._row = row
        self.rowcount = 1

    def mappings(self):
        return self

    def first(self):
        return self._row


class FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.executed: list[str] = []

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt).split()[0].upper())
        # only the SELECT returns a row
        if "SELECT" in str(stmt).upper():
            return FakeResult(self.row)
        return FakeResult()

    async def commit(self):
        ...


@pytest.fixture(autouse=True)
def _fake_embed(monkeypatch):
    async def _embed(texts):
        return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(cache_service.embedder, "embed_batch", _embed)


async def test_lookup_hit_above_threshold():
    db = FakeDB(row={"id": str(uuid.uuid4()), "response": "cached answer", "hit_count": 2,
                     "age_s": 120.0, "similarity": 0.97})
    hit = await cache_service.lookup(db, str(uuid.uuid4()), "how do threads work")
    assert hit is not None and hit["response"] == "cached answer"
    assert "UPDATE" in db.executed  # hit_count bumped


async def test_lookup_miss_below_threshold():
    db = FakeDB(row={"id": str(uuid.uuid4()), "response": "x", "hit_count": 0,
                     "age_s": 1.0, "similarity": 0.80})
    assert await cache_service.lookup(db, str(uuid.uuid4()), "how do threads work") is None
    assert "UPDATE" not in db.executed


async def test_lookup_miss_when_empty():
    hit = await cache_service.lookup(FakeDB(row=None), str(uuid.uuid4()), "anything at all here")
    assert hit is None


async def test_store_skips_uncacheable():
    db = FakeDB()
    await cache_service.store(db, str(uuid.uuid4()), "today's news", "resp", "gpt-4o")
    assert db.executed == []  # never embedded / inserted


async def test_store_inserts_and_prunes():
    db = FakeDB()
    await cache_service.store(
        db, str(uuid.uuid4()), "explain how a hash map works internally", "a long answer", "gpt-4o"
    )
    assert db.executed.count("INSERT") == 1
    assert db.executed.count("DELETE") == 1  # per-user cap prune
