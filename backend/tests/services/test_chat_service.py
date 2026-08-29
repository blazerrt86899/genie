"""Unit tests for the interim chat service (CLAUDE.md §11, §16).

The LangGraph graph, repositories and Redis are faked — these tests cover the
SSE framing contract, not the LLM.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from app.services import chat_service


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakeConvRepo:
    conv = SimpleNamespace(id=uuid.uuid4(), title=None)
    touched: int = 0
    titled: str | None = None

    def __init__(self, _db) -> None: ...

    async def create(self, user_id, title=None):
        FakeConvRepo.conv = SimpleNamespace(id=uuid.uuid4(), user_id=user_id, title=title)
        return FakeConvRepo.conv

    async def get_for_user(self, conversation_id, user_id):
        return FakeConvRepo.conv if conversation_id == FakeConvRepo.conv.id else None

    async def touch(self, conversation_id):
        FakeConvRepo.touched += 1

    async def set_title(self, conversation_id, user_id, title):
        FakeConvRepo.titled = title
        FakeConvRepo.conv.title = title


class FakeMsgRepo:
    added: list[tuple[str, str]] = []
    last_metadata: dict | None = None

    def __init__(self, _db) -> None: ...

    async def add_message(self, conversation_id, user_id, role, content, metadata=None):
        FakeMsgRepo.added.append((role, content))
        FakeMsgRepo.last_metadata = metadata
        return SimpleNamespace(id=uuid.uuid4())


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeMsgRepo.added = []
    FakeConvRepo.touched = 0
    FakeConvRepo.titled = None
    FakeConvRepo.conv = SimpleNamespace(id=uuid.uuid4(), title=None)
    monkeypatch.setattr(chat_service, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(chat_service, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(chat_service, "settings", SimpleNamespace(llm_configured=True))

    async def _fake_title(_u, _a):
        return "Learn ML"

    monkeypatch.setattr(chat_service, "generate_title", _fake_title)


def _user():
    return SimpleNamespace(id=uuid.uuid4())


async def test_create_turn_persists_user_message_and_stashes_run():
    redis = FakeRedis()
    user = _user()
    run_id, conversation_id = await chat_service.create_turn(
        db=None, redis=redis, user=user, message="hello", conversation_id=None
    )
    assert ("user", "hello") in FakeMsgRepo.added
    stashed = json.loads(redis.store[f"run:{run_id}"])
    assert stashed == {"conversation_id": conversation_id, "message": "hello"}


async def test_stream_turn_emits_tokens_then_done(monkeypatch):
    redis = FakeRedis()
    user = _user()
    run_id, conversation_id = await chat_service.create_turn(
        db=None, redis=redis, user=user, message="hi", conversation_id=None
    )

    async def fake_events(_state, config, version):  # noqa: ARG001
        yield {"event": "on_chain_start", "run_id": "trace-123", "parent_ids": [], "data": {}}
        for piece in ("Hel", "lo"):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "child",
                "parent_ids": ["trace-123"],
                "data": {"chunk": SimpleNamespace(content=piece)},
            }
        yield {
            "event": "on_chat_model_end",
            "parent_ids": ["trace-123"],
            "data": {"output": SimpleNamespace(usage_metadata={"total_tokens": 7})},
        }

    monkeypatch.setattr(
        chat_service, "get_runtime_graph", lambda: SimpleNamespace(astream_events=fake_events)
    )

    frames = [
        json.loads(f[6:])
        async for f in chat_service.stream_turn(None, redis, user, conversation_id, run_id)
    ]
    assert [f["type"] for f in frames] == ["token", "token", "title", "done"]
    assert [f["content"] for f in frames if f["type"] == "token"] == ["Hel", "lo"]
    assert frames[-1]["total_tokens"] == 7
    assert frames[-1]["langsmith_run_id"] == "trace-123"
    assert frames[-1]["title"] == "Learn ML"
    assert next(f for f in frames if f["type"] == "title")["title"] == "Learn ML"
    assert FakeConvRepo.titled == "Learn ML"
    assert FakeConvRepo.touched >= 2  # user msg + assistant msg
    assert ("assistant", "Hello") in FakeMsgRepo.added
    assert FakeMsgRepo.last_metadata == {"langsmith_run_id": "trace-123"}
    assert f"run:{run_id}" not in redis.store  # consumed


async def test_stream_turn_unknown_run_emits_error_then_done():
    redis = FakeRedis()
    frames = [
        json.loads(f[6:])
        async for f in chat_service.stream_turn(
            None, redis, _user(), str(uuid.uuid4()), "missing"
        )
    ]
    assert [f["type"] for f in frames] == ["error", "done"]
    assert frames[0]["code"] == "run_not_found"
