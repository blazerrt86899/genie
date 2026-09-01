"""Knowledge-Base document endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import documents as docs_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.services.document_service import DocumentError
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_PID = uuid.uuid4()
_NOW = datetime.now(UTC)


def _doc(**kw):
    return SimpleNamespace(
        id=kw.get("id", uuid.uuid4()),
        project_id=_PID,
        filename="a.md",
        kind="md",
        status=kw.get("status", "queued"),
        phase=kw.get("phase", "upload"),
        error=None,
        stats={},
        byte_size=10,
        created_at=_NOW,
        processed_at=None,
    )


class FakeSvc:
    store: dict = {}

    @staticmethod
    async def create_and_enqueue(db, user_id, project_id, filename, data):
        if not filename.endswith((".pdf", ".md", ".txt")):
            raise DocumentError("bad type")
        d = _doc()
        FakeSvc.store[str(d.id)] = d
        return d

    @staticmethod
    async def list_for_project(db, user_id, project_id):
        return list(FakeSvc.store.values())

    @staticmethod
    async def get(db, user_id, document_id):
        return FakeSvc.store.get(str(document_id))

    @staticmethod
    async def list_chunks(db, user_id, document_id, *, limit, offset):
        return [{"chunk_index": 0, "content": "hi", "token_count": 1, "metadata": {}}]

    @staticmethod
    async def delete(db, user_id, document_id):
        return FakeSvc.store.pop(str(document_id), None) is not None


class FakeProjectRepo:
    def __init__(self, _db): ...

    async def get_for_user(self, pid, uid):
        return SimpleNamespace(id=pid) if pid == _PID else None


class FakeChunkRepo:
    def __init__(self, _db): ...

    async def count_for_document(self, did):
        return 3


@pytest.fixture
def client(monkeypatch):
    FakeSvc.store = {}
    monkeypatch.setattr(docs_ep, "document_service", FakeSvc)
    monkeypatch.setattr(docs_ep, "ProjectRepository", FakeProjectRepo)
    monkeypatch.setattr(docs_ep, "DocumentChunkRepository", FakeChunkRepo)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_upload_and_list(client):
    async with client as c:
        up = await c.post(
            "/api/v1/documents",
            data={"project_id": str(_PID)},
            files={"file": ("notes.md", b"# hi", "text/markdown")},
        )
        assert up.status_code == 201
        assert up.json()["chunk_count"] == 3
        lst = await c.get(f"/api/v1/documents?project_id={_PID}")
    assert lst.status_code == 200 and len(lst.json()) == 1


async def test_upload_bad_type_422(client):
    async with client as c:
        r = await c.post(
            "/api/v1/documents",
            data={"project_id": str(_PID)},
            files={"file": ("x.png", b"x", "image/png")},
        )
    assert r.status_code == 422


async def test_upload_unknown_project_404(client):
    async with client as c:
        r = await c.post(
            "/api/v1/documents",
            data={"project_id": str(uuid.uuid4())},
            files={"file": ("x.md", b"x", "text/markdown")},
        )
    assert r.status_code == 404


async def test_chunks_and_delete(client):
    async with client as c:
        up = await c.post(
            "/api/v1/documents",
            data={"project_id": str(_PID)},
            files={"file": ("n.md", b"# hi", "text/markdown")},
        )
        did = up.json()["id"]
        ch = await c.get(f"/api/v1/documents/{did}/chunks")
        assert ch.status_code == 200 and ch.json()[0]["chunk_index"] == 0
        d = await c.delete(f"/api/v1/documents/{did}")
        missing = await c.delete(f"/api/v1/documents/{uuid.uuid4()}")
    assert d.status_code == 204 and missing.status_code == 404
