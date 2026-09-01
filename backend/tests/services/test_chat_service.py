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


def _conv(*, title=None, project_id=None, model=None, **kw):
    return SimpleNamespace(
        id=uuid.uuid4(), title=title, project_id=project_id, model=model, **kw
    )


class FakeConvRepo:
    conv = _conv()
    touched: int = 0
    titled: str | None = None
    model_set: str | None = None

    def __init__(self, _db) -> None: ...

    async def create(self, user_id, title=None, project_id=None, model=None):
        FakeConvRepo.conv = _conv(
            user_id=user_id, title=title, project_id=project_id, model=model
        )
        return FakeConvRepo.conv

    async def get_for_user(self, conversation_id, user_id):
        return FakeConvRepo.conv if conversation_id == FakeConvRepo.conv.id else None

    async def touch(self, conversation_id):
        FakeConvRepo.touched += 1

    async def set_title(self, conversation_id, user_id, title):
        FakeConvRepo.titled = title
        FakeConvRepo.conv.title = title

    async def set_model(self, conversation_id, user_id, model):
        FakeConvRepo.model_set = model
        FakeConvRepo.conv.model = model


class FakeMsgRepo:
    added: list[tuple[str, str]] = []
    added_full: list[tuple[str, str, dict | None]] = []
    last_metadata: dict | None = None

    def __init__(self, _db) -> None: ...

    async def add_message(
        self, conversation_id, user_id, role, content, metadata=None, created_at=None
    ):
        FakeMsgRepo.added.append((role, content))
        FakeMsgRepo.added_full.append((role, content, metadata))
        FakeMsgRepo.last_metadata = metadata
        return SimpleNamespace(id=uuid.uuid4())


class FakeProjectRepo:
    instructions: str | None = None

    def __init__(self, _db) -> None: ...

    async def get_for_user(self, project_id, user_id):
        return SimpleNamespace(
            id=project_id, instructions=FakeProjectRepo.instructions, rag_settings={}
        )


class FakeDocRepo:
    def __init__(self, _db) -> None: ...

    async def count_ready_for_project(self, project_id):
        return 0


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeMsgRepo.added = []
    FakeMsgRepo.added_full = []
    FakeConvRepo.touched = 0
    FakeConvRepo.titled = None
    FakeConvRepo.model_set = None
    FakeConvRepo.conv = _conv()
    FakeProjectRepo.instructions = None
    monkeypatch.setattr(chat_service, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(chat_service, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(chat_service, "ProjectRepository", FakeProjectRepo)
    monkeypatch.setattr(chat_service, "DocumentRepository", FakeDocRepo)
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
    assert stashed == {
        "conversation_id": conversation_id,
        "message": "hello",
        "client_hour": None,
        "attachment_ids": [],
    }


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
                "metadata": {"langgraph_node": "synthesiser"},
                "data": {"chunk": SimpleNamespace(content=piece)},
            }
        yield {
            "event": "on_chat_model_end",
            "parent_ids": ["trace-123"],
            "data": {"output": SimpleNamespace(usage_metadata={"total_tokens": 7})},
        }

    async def fake_get_state(_config):
        return SimpleNamespace(values={"messages": [SimpleNamespace(content="Hello")]})

    monkeypatch.setattr(
        chat_service,
        "get_runtime_graph",
        lambda: SimpleNamespace(astream_events=fake_events, aget_state=fake_get_state),
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


async def test_stream_turn_splits_segment_and_answer_into_two_messages(monkeypatch):
    redis = FakeRedis()
    user = _user()
    run_id, conversation_id = await chat_service.create_turn(
        db=None, redis=redis, user=user, message="hi, weather?", conversation_id=None
    )

    def custom(name, data):
        return {"event": "on_custom_event", "name": name, "parent_ids": [], "data": data}

    async def fake_events(_state, config, version):  # noqa: ARG001
        yield custom("message_agents", {"agents": ["greeting"]})
        yield custom("segment", {"agent": "greeting", "text": "Good evening!"})
        yield custom("message_break", {})
        yield custom("message_agents", {"agents": ["web_search"]})
        for piece in ("It is ", "22C."):
            yield {
                "event": "on_chat_model_stream",
                "parent_ids": [],
                "metadata": {"langgraph_node": "synthesiser"},
                "data": {"chunk": SimpleNamespace(content=piece)},
            }

    async def fake_get_state(_config):
        return SimpleNamespace(values={"messages": []})

    monkeypatch.setattr(
        chat_service,
        "get_runtime_graph",
        lambda: SimpleNamespace(astream_events=fake_events, aget_state=fake_get_state),
    )

    frames = [
        json.loads(f[6:])
        async for f in chat_service.stream_turn(None, redis, user, conversation_id, run_id)
    ]
    assert [f["type"] for f in frames] == [
        "message_agents",
        "token",
        "message_break",
        "message_agents",
        "token",
        "token",
        "title",
        "done",
    ]
    assert [f["content"] for f in frames if f["type"] == "token"] == [
        "Good evening!",
        "It is ",
        "22C.",
    ]
    assert [f["agents"] for f in frames if f["type"] == "message_agents"] == [
        ["greeting"],
        ["web_search"],
    ]
    assistant = [(c, m) for r, c, m in FakeMsgRepo.added_full if r == "assistant"]
    assert assistant[0] == ("Good evening!", {"agents": ["greeting"]})
    assert assistant[1][0] == "It is 22C."
    assert assistant[1][1]["agents"] == ["web_search"]


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


async def test_project_instructions_reach_the_graph(monkeypatch):
    redis = FakeRedis()
    user = _user()
    run_id, conversation_id = await chat_service.create_turn(
        db=None, redis=redis, user=user, message="hi", conversation_id=None
    )
    FakeConvRepo.conv.project_id = uuid.uuid4()
    FakeProjectRepo.instructions = "Always reply in French."

    seen: dict = {}

    async def fake_events(state, config, version):  # noqa: ARG001
        seen["state"] = state
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "synthesiser"},
            "data": {"chunk": SimpleNamespace(content="ok")},
        }

    async def fake_get_state(_config):
        return SimpleNamespace(values={"messages": [SimpleNamespace(content="ok")]})

    monkeypatch.setattr(
        chat_service,
        "get_runtime_graph",
        lambda: SimpleNamespace(astream_events=fake_events, aget_state=fake_get_state),
    )

    _ = [f async for f in chat_service.stream_turn(None, redis, user, conversation_id, run_id)]
    assert seen["state"]["project_instructions"] == "Always reply in French."
