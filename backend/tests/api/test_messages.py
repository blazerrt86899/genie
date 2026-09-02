"""POST /api/v1/messages/{id}/feedback — 👍/👎 (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import messages as msg_ep
from app.core.clerk import get_current_user
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())


@pytest.fixture
def env(monkeypatch):
    store = {"meta": {"langsmith_run_id": "run-123"}}
    ls_calls: list[tuple] = []

    class FakeMsgRepo:
        def __init__(self, _db): ...

        async def set_feedback(self, mid, uid, vote):
            if str(mid) != store["id"]:
                return None
            m = dict(store["meta"])
            if vote:
                m["feedback"] = vote
            else:
                m.pop("feedback", None)
            store["meta"] = m
            return SimpleNamespace(message_metadata=m)

    monkeypatch.setattr(msg_ep, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(
        msg_ep, "send_run_feedback", lambda *a, **k: ls_calls.append((a, k)) or True
    )

    store["id"] = str(uuid.uuid4())

    def _db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: _USER
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), store, ls_calls


async def test_up_then_down_then_clear(env):
    client, store, ls = env
    mid = store["id"]
    async with client as c:
        r1 = await c.post(f"/api/v1/messages/{mid}/feedback", json={"vote": "up"})
        assert r1.status_code == 200 and r1.json()["vote"] == "up"
        assert store["meta"]["feedback"] == "up"
        assert ls and ls[0][1]["score"] == 1.0  # score for 👍

        await c.post(f"/api/v1/messages/{mid}/feedback", json={"vote": "down"})
        assert store["meta"]["feedback"] == "down"

        r3 = await c.post(f"/api/v1/messages/{mid}/feedback", json={"vote": None})
        assert r3.json()["vote"] is None
        assert "feedback" not in store["meta"]


async def test_unknown_message_404(env):
    client, _, _ = env
    async with client as c:
        r = await c.post(f"/api/v1/messages/{uuid.uuid4()}/feedback", json={"vote": "up"})
    assert r.status_code == 404


async def test_bad_vote_422(env):
    client, store, _ = env
    async with client as c:
        r = await c.post(f"/api/v1/messages/{store['id']}/feedback", json={"vote": "meh"})
    assert r.status_code == 422
