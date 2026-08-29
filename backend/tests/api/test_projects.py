"""Project CRUD endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import projects as proj_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_NOW = datetime.now(UTC)


def _project(name="Demo", instructions=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        description=None,
        instructions=instructions,
        created_at=_NOW,
        updated_at=_NOW,
    )


class FakeProjectRepo:
    store: dict = {}

    def __init__(self, _db) -> None: ...

    async def create(self, user_id, name, description=None, instructions=None):
        p = _project(name, instructions)
        FakeProjectRepo.store[str(p.id)] = p
        return p

    async def get_for_user(self, project_id, user_id):
        return FakeProjectRepo.store.get(str(project_id))

    async def list_for_user(self, user_id):
        return [(p, 2) for p in FakeProjectRepo.store.values()]

    async def update(self, project_id, user_id, **fields):
        p = FakeProjectRepo.store.get(str(project_id))
        if p is None:
            return None
        for k, v in fields.items():
            setattr(p, k, v)
        return p

    async def delete_for_user(self, project_id, user_id):
        return FakeProjectRepo.store.pop(str(project_id), None) is not None


class FakeConvRepo:
    def __init__(self, _db) -> None: ...

    async def list_for_project(self, project_id, user_id):
        return []


@pytest.fixture
def client(monkeypatch):
    FakeProjectRepo.store = {}
    monkeypatch.setattr(proj_ep, "ProjectRepository", FakeProjectRepo)
    monkeypatch.setattr(proj_ep, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(
        proj_ep,
        "get_runtime_graph",
        lambda: SimpleNamespace(checkpointer=SimpleNamespace(adelete_thread=_noop)),
    )

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _noop(*_a, **_k):
    return None


async def test_project_crud(client):
    async with client as c:
        created = await c.post(
            "/api/v1/projects", json={"name": "French", "instructions": "Reply in French."}
        )
        assert created.status_code == 201
        pid = created.json()["id"]

        listed = await c.get("/api/v1/projects")
        assert listed.status_code == 200
        assert listed.json()[0]["conversation_count"] == 2

        detail = await c.get(f"/api/v1/projects/{pid}")
        assert detail.status_code == 200
        assert detail.json()["conversations"] == []

        patched = await c.patch(
            f"/api/v1/projects/{pid}", json={"instructions": "Reply in Spanish."}
        )
        assert patched.json()["instructions"] == "Reply in Spanish."

        gone = await c.delete(f"/api/v1/projects/{pid}")
        assert gone.status_code == 204

        assert (await c.get(f"/api/v1/projects/{pid}")).status_code == 404


async def test_missing_project_is_404(client):
    async with client as c:
        assert (await c.get(f"/api/v1/projects/{uuid.uuid4()}")).status_code == 404
        assert (await c.get("/api/v1/projects/not-a-uuid")).status_code == 404
        assert (await c.delete(f"/api/v1/projects/{uuid.uuid4()}")).status_code == 404
