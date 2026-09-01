"""GET /api/v1/models — the composer's model picker catalog (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.agents.models import ModelSpec
from app.api.v1.endpoints import models as models_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())

_FAKE_CATALOG = [
    ModelSpec("gpt-4o", "GPT-4o", "openai", "gpt-4o-2024-08-06", "OpenAI · balanced"),
    ModelSpec("groq-oss-120b", "GPT-OSS 120B", "groq", "openai/gpt-oss-120b", "Groq · fast"),
]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(models_ep, "available_models", lambda: _FAKE_CATALOG)
    monkeypatch.setattr(models_ep, "default_model_id", lambda: "groq-oss-120b")

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_lists_catalog_with_default(client):
    async with client as c:
        resp = await c.get("/api/v1/models")
    assert resp.status_code == 200
    body = resp.json()
    assert [m["id"] for m in body["models"]] == ["gpt-4o", "groq-oss-120b"]
    assert body["models"][0]["provider"] == "openai"
    assert body["default"] == "groq-oss-120b"


async def test_requires_auth():
    app = create_app()

    def _fake_db():
        yield None

    app.dependency_overrides[get_db] = _fake_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/api/v1/models")
    assert resp.status_code in (401, 403)
