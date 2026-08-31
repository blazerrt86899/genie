"""Task board endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import tasks as tasks_ep
from app.core.clerk import get_current_user
from app.core.exceptions import NotFoundError
from app.db.models.task import TASK_STATUSES
from app.db.session import get_db
from app.main import create_app
from app.services.task_service import TaskValidationError
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_NOW = datetime.now(UTC)


def _task(title="buy milk", status="todo", **kw):
    return SimpleNamespace(
        id=kw.get("id", uuid.uuid4()),
        title=title,
        description=kw.get("description"),
        status=status,
        conversation_id=kw.get("conversation_id"),
        source_agent="api",
        created_at=_NOW,
        updated_at=_NOW,
        archived_at=kw.get("archived_at"),
    )


class FakeSvc:
    store: dict[str, SimpleNamespace] = {}

    @staticmethod
    async def create_task(db, user_id, title, *, description=None, source_agent=None, **kw):
        t = _task(title=title, description=description)
        FakeSvc.store[str(t.id)] = t
        return t

    @staticmethod
    async def list_tasks(db, user_id, *, include_archived=False):
        return [
            t for t in FakeSvc.store.values() if include_archived or t.status != "archived"
        ]

    @staticmethod
    async def get_task(db, user_id, task_id):
        t = FakeSvc.store.get(str(task_id))
        if t is None:
            raise NotFoundError("task not found")
        return t

    @staticmethod
    async def move_task(db, user_id, task_id, status):
        if status not in TASK_STATUSES:
            raise TaskValidationError(f"bad status {status}")
        t = await FakeSvc.get_task(db, user_id, task_id)
        t.status = status
        return t

    @staticmethod
    async def update_details(db, user_id, task_id, **fields):
        t = await FakeSvc.get_task(db, user_id, task_id)
        if fields.get("title") is not None:
            t.title = fields["title"]
        if "description" in fields:
            t.description = fields["description"]
        return t

    @staticmethod
    async def summarize_task(db, user_id, task_id):
        t = await FakeSvc.get_task(db, user_id, task_id)
        t.description = "A crisp 3-line summary of the chat."
        return t

    @staticmethod
    async def archive_done(db, user_id):
        n = 0
        for t in FakeSvc.store.values():
            if t.status == "done":
                t.status = "archived"
                n += 1
        return n

    @staticmethod
    async def delete_task(db, user_id, task_id):
        if FakeSvc.store.pop(str(task_id), None) is None:
            raise NotFoundError("task not found")


@pytest.fixture
def client(monkeypatch):
    FakeSvc.store = {}
    monkeypatch.setattr(tasks_ep, "task_service", FakeSvc)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_task_lifecycle(client):
    async with client as c:
        created = await c.post("/api/v1/tasks", json={"title": "buy milk"})
        assert created.status_code == 201
        tid = created.json()["id"]

        board = await c.get("/api/v1/tasks")
        assert [t["title"] for t in board.json()] == ["buy milk"]

        moved = await c.patch(f"/api/v1/tasks/{tid}", json={"status": "done"})
        assert moved.json()["status"] == "done"

        edited = await c.patch(f"/api/v1/tasks/{tid}", json={"description": "2%"})
        assert edited.json()["description"] == "2%"

        archived = await c.post("/api/v1/tasks/archive-done")
        assert archived.json() == {"archived": 1}
        assert (await c.get("/api/v1/tasks")).json() == []
        assert len((await c.get("/api/v1/tasks?include_archived=true")).json()) == 1

        gone = await c.delete(f"/api/v1/tasks/{tid}")
        assert gone.status_code == 204


async def test_summarize_endpoint(client):
    async with client as c:
        tid = (await c.post("/api/v1/tasks", json={"title": "x"})).json()["id"]
        r = await c.post(f"/api/v1/tasks/{tid}/summarize")
        assert r.status_code == 200
        assert r.json()["description"].startswith("A crisp 3-line summary")


async def test_bad_status_is_422(client):
    async with client as c:
        tid = (await c.post("/api/v1/tasks", json={"title": "x"})).json()["id"]
        r = await c.patch(f"/api/v1/tasks/{tid}", json={"status": "nope"})
        assert r.status_code == 422


async def test_missing_task_404(client):
    async with client as c:
        r = await c.get(f"/api/v1/tasks/{uuid.uuid4()}")
        assert r.status_code == 404
