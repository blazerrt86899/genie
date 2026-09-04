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
    search_args: tuple = ()

    def __init__(self, _db) -> None: ...

    async def list_for_user(self, user_id, limit=50):
        # repo is responsible for ordering — return newest-activity first
        return [_B, _A]

    async def delete_for_user(self, conversation_id, user_id):
        return str(conversation_id) == str(_A.id)

    async def search(self, user_id, query, limit=30):
        FakeConvRepo.search_args = (user_id, query, limit)
        if query == "newer":
            return [(_B, None)]  # title match, no snippet
        if query == "inside":
            return [(_A, "…a message that mentions inside somewhere…")]
        return []


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


async def test_search_title_match(client):
    async with client as c:
        resp = await c.get("/api/v1/conversations/search?q=newer")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["title"] for r in body] == ["Newer"]
    assert body[0]["snippet"] is None
    assert FakeConvRepo.search_args[1] == "newer"  # trimmed query passed through


async def test_search_message_match_has_snippet(client):
    async with client as c:
        resp = await c.get("/api/v1/conversations/search?q=inside&limit=5")
    body = resp.json()
    assert body[0]["title"] == "Older"
    assert "inside" in body[0]["snippet"]
    assert FakeConvRepo.search_args[2] == 5


async def test_search_no_match_is_empty(client):
    async with client as c:
        resp = await c.get("/api/v1/conversations/search?q=zzzznope")
    assert resp.status_code == 200 and resp.json() == []


async def test_search_missing_q_is_422(client):
    async with client as c:
        resp = await c.get("/api/v1/conversations/search")
    assert resp.status_code == 422


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
        id=uuid.uuid4(), title="X", project_id=None, model=None, pinned=False, unread=False,
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

        async def set_flag(self, cid, uid, **v):
            for k, val in v.items():
                setattr(conv, k, val)

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


# ─── GET /conversations/{id} — message metadata passthrough ──────────────────


@pytest.fixture
def get_client(monkeypatch):
    conv = SimpleNamespace(
        id=uuid.uuid4(), title="X", project_id=None, model=None, pinned=False,
        unread=False, share_token=None, shared_at=None,
        created_at=_NOW, last_message_at=_NOW,
    )
    msg = SimpleNamespace(
        id=uuid.uuid4(),
        role="assistant",
        content="Here's your report.",
        created_at=_NOW,
        message_metadata={
            "agents": ["file_creator"],
            "thinking": "Let me plan the report structure first.",
            "thinking_ms": 4200,
            "files": [
                {
                    "id": str(uuid.uuid4()),
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "byte_size": 5000,
                    "summary": "A short report",
                }
            ],
        },
    )

    class FakeConvRepo3:
        def __init__(self, _db): ...

        async def get_for_user(self, cid, uid):
            return conv if cid == conv.id else None

        async def mark_read(self, cid, uid):
            conv.unread = False

    class FakeMsgRepo:
        def __init__(self, _db): ...

        async def list_for_conversation(self, cid):
            return [msg]

    monkeypatch.setattr(conv_ep, "ConversationRepository", FakeConvRepo3)
    monkeypatch.setattr(conv_ep, "MessageRepository", FakeMsgRepo)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), conv, msg


async def test_get_conversation_message_carries_thinking_and_files(get_client):
    client, conv, msg = get_client
    async with client as c:
        resp = await c.get(f"/api/v1/conversations/{conv.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["messages"]) == 1
    m = body["messages"][0]
    assert m["thinking"] == "Let me plan the report structure first."
    assert m["thinking_ms"] == 4200
    assert m["files"][0]["filename"] == "report.pdf"
    assert m["files"][0]["id"] == msg.message_metadata["files"][0]["id"]


async def test_get_conversation_message_defaults_when_absent(get_client):
    client, conv, msg = get_client
    msg.message_metadata = {}
    async with client as c:
        resp = await c.get(f"/api/v1/conversations/{conv.id}")
    m = resp.json()["messages"][0]
    assert m["thinking"] is None
    assert m["thinking_ms"] is None
    assert m["files"] == []


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


async def test_patch_pin_and_unread(patch_client):
    client, conv, _ = patch_client
    async with client as c:
        r1 = await c.patch(f"/api/v1/conversations/{conv.id}", json={"pinned": True})
        r2 = await c.patch(f"/api/v1/conversations/{conv.id}", json={"unread": True})
    assert r1.json()["pinned"] is True
    assert r2.json()["unread"] is True and conv.pinned is True  # pin unaffected
