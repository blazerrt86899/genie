"""POST/DELETE /api/v1/attachments (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import attachments as att_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.services.attachment_service import AttachmentError
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())


class FakeSvc:
    deleted: list[str] = []

    @staticmethod
    async def create_attachment(db, user_id, filename, data):
        if not filename.endswith((".pdf", ".txt", ".md")):
            raise AttachmentError("unsupported file type")
        return SimpleNamespace(
            id=uuid.uuid4(), filename=filename, kind=filename.split(".")[-1],
            char_count=len(data), token_estimate=len(data) // 4,
        )

    @staticmethod
    async def delete_attachment(db, user_id, attachment_id):
        FakeSvc.deleted.append(attachment_id)
        return attachment_id == "real"


@pytest.fixture
def client(monkeypatch):
    FakeSvc.deleted = []
    monkeypatch.setattr(att_ep, "attachment_service", FakeSvc)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_upload_txt(client):
    async with client as c:
        resp = await c.post(
            "/api/v1/attachments",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "txt"
    assert body["char_count"] == 11


async def test_upload_bad_type_422(client):
    async with client as c:
        resp = await c.post(
            "/api/v1/attachments",
            files={"file": ("photo.png", b"\x89PNG", "image/png")},
        )
    assert resp.status_code == 422


async def test_delete(client):
    async with client as c:
        ok = await c.delete("/api/v1/attachments/real")
        missing = await c.delete("/api/v1/attachments/nope")
    assert ok.status_code == 204
    assert missing.status_code == 404


async def test_requires_auth():
    app = create_app()

    def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post(
            "/api/v1/attachments",
            files={"file": ("x.txt", b"x", "text/plain")},
        )
    assert resp.status_code in (401, 403)
