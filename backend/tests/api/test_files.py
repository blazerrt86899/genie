"""Generated-file download endpoint (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import files as files_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_OTHER_USER = SimpleNamespace(id=uuid.uuid4())
_FILE_ID = uuid.uuid4()


class FakeFileService:
    @staticmethod
    async def download_bytes(_db, user_id, file_id):
        if file_id == _FILE_ID and user_id == _USER.id:
            row = SimpleNamespace(
                id=file_id, filename="report.pdf", mime_type="application/pdf"
            )
            return row, b"%PDF-fake-bytes"
        return None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(files_ep, "file_service", FakeFileService)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_download_returns_bytes_with_headers(client):
    async with client as c:
        r = await c.get(f"/api/v1/files/{_FILE_ID}/download")
    assert r.status_code == 200
    assert r.content == b"%PDF-fake-bytes"
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="report.pdf"' in r.headers["content-disposition"]


async def test_download_unknown_file_404(client):
    async with client as c:
        r = await c.get(f"/api/v1/files/{uuid.uuid4()}/download")
    assert r.status_code == 404


async def test_download_bad_id_404(client):
    async with client as c:
        r = await c.get("/api/v1/files/not-a-uuid/download")
    assert r.status_code == 404


async def test_download_another_users_file_404(monkeypatch):
    monkeypatch.setattr(files_ep, "file_service", FakeFileService)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _OTHER_USER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(f"/api/v1/files/{_FILE_ID}/download")
    assert r.status_code == 404
