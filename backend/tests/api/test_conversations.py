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

_A = SimpleNamespace(id=uuid.uuid4(), title="Older", created_at=_NOW - timedelta(hours=2),
                     last_message_at=_NOW - timedelta(hours=2))
_B = SimpleNamespace(id=uuid.uuid4(), title="Newer", created_at=_NOW - timedelta(hours=1),
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
