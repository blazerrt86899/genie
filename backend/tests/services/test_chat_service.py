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
    conv = SimpleNamespace(id=uuid.uuid4(), title="t")

    def __init__(self, _db) -> None: ...

    async def create(self, user_id, title):
        FakeConvRepo.conv = SimpleNamespace(id=uuid.uuid4(), user_id=user_id, title=title)
        return FakeConvRepo.conv

    async def get_for_user(self, conversation_id, user_id):
        return FakeConvRepo.conv if conversation_id == FakeConvRepo.conv.id else None


class FakeMsgRepo:
    added: list[tuple[str, str]] = []

    def __init__(self, _db) -> None: ...

    async def add_message(self, conversation_id, user_id, role, content):
        FakeMsgRepo.added.append((role, content))
        return SimpleNamespace(id=uuid.uuid4())


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeMsgRepo.added = []
    monkeypatch.setattr(chat_service, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(chat_service, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(chat_service, "settings", SimpleNamespace(llm_configured=True))


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
        for piece in ("Hel", "lo"):
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": SimpleNamespace(content=piece)},
            }
        yield {
            "event": "on_chat_model_end",
            "data": {"output": SimpleNamespace(usage_metadata={"total_tokens": 7})},
        }

    monkeypatch.setattr(
        chat_service, "get_runtime_graph", lambda: SimpleNamespace(astream_events=fake_events)
    )

    frames = [
        json.loads(f[6:])
        async for f in chat_service.stream_turn(None, redis, user, conversation_id, run_id)
    ]
    assert [f["type"] for f in frames] == ["token", "token", "done"]
    assert [f["content"] for f in frames if f["type"] == "token"] == ["Hel", "lo"]
    assert frames[-1]["total_tokens"] == 7
    assert ("assistant", "Hello") in FakeMsgRepo.added
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
