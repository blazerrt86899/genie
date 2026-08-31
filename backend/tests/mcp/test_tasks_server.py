"""FastMCP tasks server (CLAUDE.md §22) — in-memory client, task_service faked."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.mcp import tasks_server
from fastmcp import Client

_UID = str(uuid.uuid4())


def _fake_task(title="buy milk", status="todo", **kw):
    return SimpleNamespace(
        id=kw.get("id", uuid.uuid4()),
        title=title,
        description=kw.get("description"),
        status=status,
        conversation_id=kw.get("conversation_id"),
        source_agent="task_creator",
        created_at=SimpleNamespace(isoformat=lambda: "2026-08-31T00:00:00+00:00"),
        updated_at=SimpleNamespace(isoformat=lambda: "2026-08-31T00:00:00+00:00"),
        archived_at=None,
    )


class _FakeSvc:
    created: list[str] = []

    @staticmethod
    async def create_task(db, user_id, title, **kw):
        _FakeSvc.created.append(title)
        return _fake_task(
            title=title,
            description=kw.get("description"),
            conversation_id=kw.get("conversation_id"),
        )

    @staticmethod
    async def list_tasks(db, user_id, *, include_archived=False):
        return [_fake_task("a"), _fake_task("b", status="done")]

    @staticmethod
    async def find_task(db, user_id, query):
        return _fake_task("quarterly report") if "report" in query else None

    @staticmethod
    async def move_task(db, user_id, task_id, status):
        return _fake_task(status=status)

    @staticmethod
    async def archive_done(db, user_id):
        return 3

    @staticmethod
    def to_dict(t):
        return {"id": str(t.id), "title": t.title, "status": t.status}


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _FakeSvc.created = []
    for name in ("create_task", "list_tasks", "find_task", "move_task", "archive_done", "to_dict"):
        monkeypatch.setattr(tasks_server.task_service, name, getattr(_FakeSvc, name))
    monkeypatch.setattr(tasks_server, "get_sessionmaker", lambda: (lambda: _FakeSession()))


async def test_tools_are_registered():
    async with Client(tasks_server.mcp) as c:
        names = {t.name for t in await c.list_tools()}
    assert {"create_task", "list_tasks", "set_task_status", "archive_done_tasks"} <= names


async def test_create_task_tool():
    async with Client(tasks_server.mcp) as c:
        r = await c.call_tool("create_task", {"user_id": _UID, "title": "buy milk"})
    assert r.data["title"] == "buy milk"
    assert _FakeSvc.created == ["buy milk"]


async def test_set_status_and_archive():
    async with Client(tasks_server.mcp) as c:
        moved = await c.call_tool(
            "set_task_status", {"user_id": _UID, "task_id": str(uuid.uuid4()), "status": "done"}
        )
        archived = await c.call_tool("archive_done_tasks", {"user_id": _UID})
    assert moved.data["status"] == "done"
    assert archived.data == 3
