"""chat_service.regenerate_turn — truncate at a message and re-run (CLAUDE.md §9)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.services import chat_service

_USER = SimpleNamespace(id=uuid.uuid4())
_CONV_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


def _msg(i: int, role: str, content: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        content=content,
        created_at=_NOW + timedelta(minutes=i),
        message_metadata={},
    )


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key, _ttl, value):
        self.store[key] = value


@pytest.fixture
def env(monkeypatch):
    # u1 → a1 → u2 → a2
    rows = [
        _msg(0, "user", "first question"),
        _msg(1, "assistant", "first answer"),
        _msg(2, "user", "second question"),
        _msg(3, "assistant", "second answer"),
    ]
    state = {"rows": rows, "deleted_after": None, "edited": None, "thread_deleted": False}

    class FakeConvRepo:
        def __init__(self, _db): ...

        async def get_for_user(self, cid, uid):
            return SimpleNamespace(id=cid) if cid == _CONV_ID and uid == _USER.id else None

        async def touch(self, cid): ...

    class FakeMsgRepo:
        def __init__(self, _db): ...

        async def list_for_conversation(self, cid, limit=200):
            return list(state["rows"])

        async def set_content(self, mid, uid, content):
            state["edited"] = (mid, content)

        async def delete_after(self, cid, after, *, inclusive=False):
            before = len(state["rows"])
            state["rows"] = [m for m in state["rows"] if m.created_at <= after]
            state["deleted_after"] = after
            return before - len(state["rows"])

    def _graph():
        cp = SimpleNamespace()

        async def _del(_tid):
            state["thread_deleted"] = True

        cp.adelete_thread = _del
        return SimpleNamespace(checkpointer=cp)

    monkeypatch.setattr(chat_service, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(chat_service, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(chat_service, "get_runtime_graph", _graph)
    return state


async def _call(redis, state, target_role, edit=None):
    rows = state["rows"]
    target = next(m for m in rows if m.role == target_role and m.content.startswith("first"))
    return await chat_service.regenerate_turn(
        None, redis, _USER, str(_CONV_ID), str(target.id), edit
    )


async def test_regenerate_assistant_drops_it_and_the_tail(env):
    redis = FakeRedis()
    run_id, cid = await _call(redis, env, "assistant")
    assert cid == str(_CONV_ID)
    # only the first user message survives
    assert [m.role for m in env["rows"]] == ["user"]
    assert env["thread_deleted"] is True
    payload = json.loads(redis.store[f"run:{run_id}"])
    assert payload["mode"] == "regenerate"
    assert payload["message"] == "first question"


async def test_retry_user_keeps_it(env):
    redis = FakeRedis()
    await _call(redis, env, "user")
    assert [m.content for m in env["rows"]] == ["first question"]
    assert env["edited"] is None


async def test_edit_user_updates_content(env):
    redis = FakeRedis()
    run_id, _ = await _call(redis, env, "user", edit="  the edited question  ")
    assert env["edited"][1] == "the edited question"
    assert json.loads(redis.store[f"run:{run_id}"])["message"] == "the edited question"


async def test_unknown_message_404(env):
    with pytest.raises(ValueError, match="message not found"):
        await chat_service.regenerate_turn(
            None, FakeRedis(), _USER, str(_CONV_ID), str(uuid.uuid4()), None
        )


async def test_foreign_conversation_404(env):
    with pytest.raises(ValueError, match="conversation not found"):
        await chat_service.regenerate_turn(
            None, FakeRedis(), SimpleNamespace(id=uuid.uuid4()),
            str(_CONV_ID), str(env["rows"][0].id), None,
        )
