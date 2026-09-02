"""GET /conversations (recency order) + DELETE /conversations/{id} (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import conversations as conv_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.services import chat_service
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_NOW = datetime.now(UTC)

_A = SimpleNamespace(id=uuid.uuid4(), title="Older", project_id=None, model=None,
                     created_at=_NOW - timedelta(hours=2),
                     last_message_at=_NOW - timedelta(hours=2))
_B = SimpleNamespace(id=uuid.uuid4(), title="Newer", project_id=None, model="gpt-4o",
                     created_at=_NOW - timedelta(hours=1),
                     last_message_at=_NOW - timedelta(minutes=1))


class FakeConvRepo:
    deleted: set[str] = set()

    def __init__(self, _db) -> None: ...

    async def list_for_user(self, user_id, limit=50):
        # repo is responsible for ordering — return newest-activity first
        return [_B, _A]

    async def delete_for_user(self, conversation_id, user_id):
        return str(conversation_id) == str(_A.id)


@pytest.fixture
def client(monkeypatch):
    FakeConvRepo.deleted = set()
    monkeypatch.setattr(conv_ep, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(chat_service, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(
        chat_service,
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


async def test_list_is_recency_ordered(client):
    async with client as c:
        resp = await c.get("/api/v1/conversations")
    assert resp.status_code == 200
    body = resp.json()
    assert [row["title"] for row in body] == ["Newer", "Older"]
    assert body[0]["last_message_at"] is not None


async def test_delete_ok(client):
    async with client as c:
        resp = await c.delete(f"/api/v1/conversations/{_A.id}")
    assert resp.status_code == 204


async def test_delete_missing_is_404(client):
    async with client as c:
        resp = await c.delete(f"/api/v1/conversations/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_delete_bad_uuid_is_404(client):
    async with client as c:
        resp = await c.delete("/api/v1/conversations/not-a-uuid")
    assert resp.status_code == 404


# ─── PATCH /conversations/{id} — move into / out of a project ────────────────


@pytest.fixture
def patch_client(monkeypatch):
    conv = SimpleNamespace(
        id=uuid.uuid4(), title="X", project_id=None, model=None,
        created_at=_NOW, last_message_at=_NOW,
    )
    proj_id = uuid.uuid4()

    class FakeConvRepo2:
        def __init__(self, _db): ...

        async def get_for_user(self, cid, uid):
            return conv if cid == conv.id else None

        async def set_project(self, cid, uid, pid):
            conv.project_id = pid

        async def set_title(self, cid, uid, t):
            conv.title = t

    class FakeProjectRepo:
        def __init__(self, _db): ...

        async def get_for_user(self, pid, uid):
            return SimpleNamespace(id=pid) if pid == proj_id else None

    monkeypatch.setattr(conv_ep, "ConversationRepository", FakeConvRepo2)
    monkeypatch.setattr(conv_ep, "ProjectRepository", FakeProjectRepo)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), conv, proj_id


async def test_patch_moves_into_project(patch_client):
    client, conv, proj_id = patch_client
    async with client as c:
        resp = await c.patch(
            f"/api/v1/conversations/{conv.id}", json={"project_id": str(proj_id)}
        )
    assert resp.status_code == 200
    assert resp.json()["project_id"] == str(proj_id)


async def test_patch_detaches(patch_client):
    client, conv, _ = patch_client
    conv.project_id = uuid.uuid4()
    async with client as c:
        resp = await c.patch(
            f"/api/v1/conversations/{conv.id}", json={"project_id": None}
        )
    assert resp.status_code == 200
    assert resp.json()["project_id"] is None


async def test_patch_unknown_project_404(patch_client):
    client, conv, _ = patch_client
    async with client as c:
        resp = await c.patch(
            f"/api/v1/conversations/{conv.id}", json={"project_id": str(uuid.uuid4())}
        )
    assert resp.status_code == 404


async def test_patch_unknown_conversation_404(patch_client):
    client, _, proj_id = patch_client
    async with client as c:
        resp = await c.patch(
            f"/api/v1/conversations/{uuid.uuid4()}", json={"project_id": str(proj_id)}
        )
    assert resp.status_code == 404


async def test_patch_renames_without_touching_project(patch_client):
    client, conv, _ = patch_client
    conv.project_id = uuid.uuid4()  # already in a project
    async with client as c:
        resp = await c.patch(
            f"/api/v1/conversations/{conv.id}", json={"title": "  My renamed chat  "}
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My renamed chat"
    assert conv.project_id is not None  # project_id absent from body → untouched
