"""Clerk webhook signature verification + dispatch (CLAUDE.md §7.4, §16)."""

from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import webhooks
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from svix.webhooks import Webhook

_SECRET = "whsec_" + base64.b64encode(os.urandom(24)).decode()


class FakeUserRepo:
    calls: list[tuple[str, str]] = []

    def __init__(self, _db) -> None: ...

    async def create_from_clerk(self, data):
        FakeUserRepo.calls.append(("create", data["id"]))

    async def update_from_clerk(self, data):
        FakeUserRepo.calls.append(("update", data["id"]))

    async def soft_delete_by_clerk_id(self, clerk_id):
        FakeUserRepo.calls.append(("delete", clerk_id))


@pytest.fixture
def client(monkeypatch):
    FakeUserRepo.calls = []
    monkeypatch.setattr(webhooks, "settings", SimpleNamespace(CLERK_WEBHOOK_SECRET=_SECRET))
    monkeypatch.setattr(webhooks, "UserRepository", FakeUserRepo)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload).encode()
    msg_id = "msg_test"
    ts = datetime.now(UTC)
    sig = Webhook(_SECRET).sign(msg_id, ts, body.decode())
    return body, {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": sig,
        "content-type": "application/json",
    }


async def test_valid_user_created(client):
    body, headers = _signed({"type": "user.created", "data": {"id": "user_1"}})
    async with client as c:
        resp = await c.post("/api/v1/webhooks/clerk", content=body, headers=headers)
    assert resp.status_code == 200
    assert FakeUserRepo.calls == [("create", "user_1")]


async def test_bad_signature_rejected(client):
    body, headers = _signed({"type": "user.created", "data": {"id": "user_1"}})
    headers["svix-signature"] = "v1,bogus"
    async with client as c:
        resp = await c.post("/api/v1/webhooks/clerk", content=body, headers=headers)
    assert resp.status_code == 400
    assert FakeUserRepo.calls == []


async def test_unknown_event_is_noop(client):
    body, headers = _signed({"type": "session.created", "data": {"id": "sess_1"}})
    async with client as c:
        resp = await c.post("/api/v1/webhooks/clerk", content=body, headers=headers)
    assert resp.status_code == 200
    assert FakeUserRepo.calls == []
