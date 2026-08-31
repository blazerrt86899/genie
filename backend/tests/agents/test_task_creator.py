"""Task Creator agent (CLAUDE.md §12)."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.task_creator import agent as tc
from app.agents.task_creator.agent import run_task_creator
from app.agents.task_creator.schemas import TaskOp, TaskOps
from langchain_core.messages import HumanMessage

_UID = "user-1"


def _state(text: str, conversation_id: str | None = "conv-1"):
    return {
        "user_id": _UID,
        "conversation_id": conversation_id,
        "messages": [HumanMessage(content=text)],
    }


def _model_returning(ops: TaskOps):
    class FakeModel:
        async def ainvoke(self, _messages):
            return ops

    return SimpleNamespace(with_structured_output=lambda _m: FakeModel())


async def test_create_calls_mcp_and_emits(monkeypatch):
    calls: list[tuple[str, dict]] = []
    events: list[tuple[str, dict]] = []

    async def fake_call(name, args):
        calls.append((name, args))
        return {"id": "t1", "title": args.get("title", ""), "status": "todo"}

    async def fake_emit(name, data):
        events.append((name, data))

    monkeypatch.setattr(tc, "call_tasks_tool", fake_call)
    monkeypatch.setattr(tc, "emit", fake_emit)
    monkeypatch.setattr(
        tc,
        "get_chat_model",
        lambda **_: _model_returning(
            TaskOps(ops=[TaskOp(action="create", title="buy milk")], reply="Added it.")
        ),
    )

    res = await run_task_creator(_state("add buy milk to my todo"), {})
    assert res.stream is True
    assert calls[0][0] == "create_task"
    assert calls[0][1]["conversation_id"] == "conv-1"
    assert ("task_created", {"task": {"id": "t1", "title": "buy milk", "status": "todo"}}) in events
    assert "buy milk" in res.summary


async def test_move_finds_then_sets_status(monkeypatch):
    seq: list[str] = []

    async def fake_call(name, args):
        seq.append(name)
        if name == "find_task":
            return {"id": "t9", "title": "quarterly report"}
        return {"id": "t9", "title": "quarterly report", "status": args.get("status")}

    monkeypatch.setattr(tc, "call_tasks_tool", fake_call)
    monkeypatch.setattr(tc, "emit", lambda *_a, **_k: _noop())
    monkeypatch.setattr(
        tc,
        "get_chat_model",
        lambda **_: _model_returning(
            TaskOps(ops=[TaskOp(action="move", target="report", status="done")], reply="Done.")
        ),
    )

    res = await run_task_creator(_state("mark the report task done"), {})
    assert seq == ["find_task", "set_task_status"]
    assert "Done" in res.summary


async def test_archive_done(monkeypatch):
    async def fake_call(name, _args):
        assert name == "archive_done_tasks"
        return 2

    monkeypatch.setattr(tc, "call_tasks_tool", fake_call)
    monkeypatch.setattr(tc, "emit", lambda *_a, **_k: _noop())
    monkeypatch.setattr(
        tc,
        "get_chat_model",
        lambda **_: _model_returning(
            TaskOps(ops=[TaskOp(action="archive_done")], reply="Cleaned up.")
        ),
    )
    res = await run_task_creator(_state("archive my finished tasks"), {})
    assert "Archived 2 finished tasks" in res.summary


async def _noop():
    return None
