"""Chat share: owner control (/conversations/{id}/share) + the public read
(/public/shared/{token}). CLAUDE.md §14."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import conversations as conv_ep
from app.api.v1.endpoints import public as public_ep
from app.core.clerk import get_current_user
from app.core.redis import get_redis
from app.db.session import get_db
from app.main import create_app
from httpx import ASGITransport, AsyncClient

_USER = SimpleNamespace(id=uuid.uuid4())
_NOW = datetime.now(UTC)


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, *_a, **_k) -> None:
        return None


def _conv(**over):
    base = dict(
        id=uuid.uuid4(),
        user_id=_USER.id,
        title="WAF rule delay",
        project_id=None,
        model=None,
        pinned=False,
        unread=False,
        share_token=None,
        shared_at=None,
        created_at=_NOW,
        last_message_at=_NOW,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _msg(offset_min: int, role: str = "user", content: str = "hi"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=role,
        content=content,
        created_at=_NOW + timedelta(minutes=offset_min),
        message_metadata={},
    )


@pytest.fixture
def env(monkeypatch):
    state = {"conv": _conv(), "messages": [_msg(-10), _msg(-9, "assistant", "hello")]}

    class FakeConvRepo:
        def __init__(self, _db): ...

        async def get_for_user(self, cid, uid):
            c = state["conv"]
            return c if cid == c.id and uid == _USER.id else None

        async def get_by_share_token(self, token):
            c = state["conv"]
            return c if c.share_token == token else None

        async def set_share(self, cid, uid, token, shared_at):
            state["conv"].share_token = token
            state["conv"].shared_at = shared_at

        async def clear_share(self, cid, uid):
            state["conv"].share_token = None
            state["conv"].shared_at = None

    class FakeMsgRepo:
        def __init__(self, _db): ...

        async def list_for_conversation(self, cid, limit=200):
            return list(state["messages"])

    monkeypatch.setattr(conv_ep, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(public_ep, "ConversationRepository", FakeConvRepo)
    monkeypatch.setattr(public_ep, "MessageRepository", FakeMsgRepo)

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), state


async def test_share_lifecycle(env):
    client, state = env
    cid = state["conv"].id
    async with client as c:
        enabled = await c.post(f"/api/v1/conversations/{cid}/share")
        assert enabled.status_code == 200
        info = enabled.json()
        assert info["token"] and info["url"].endswith(info["token"])
        token = info["token"]

        # idempotent — same token
        again = await c.post(f"/api/v1/conversations/{cid}/share")
        assert again.json()["token"] == token

        # public read
        pub = await c.get(f"/api/v1/public/shared/{token}")
        assert pub.status_code == 200
        body = pub.json()
        assert body["message_count"] == 2
        assert "user_id" not in body and "project_id" not in body
        assert pub.headers["x-robots-tag"].startswith("noindex")

        # disable → public 404
        off = await c.delete(f"/api/v1/conversations/{cid}/share")
        assert off.status_code == 204
        assert (await c.get(f"/api/v1/public/shared/{token}")).status_code == 404


async def test_frozen_cutoff_excludes_later_messages(env):
    client, state = env
    cid = state["conv"].id
    async with client as c:
        token = (await c.post(f"/api/v1/conversations/{cid}/share")).json()["token"]
        # a message sent after the share cutoff
        state["messages"].append(_msg(+5, "user", "later question"))
        body = (await c.get(f"/api/v1/public/shared/{token}")).json()
    assert body["message_count"] == 2
    assert all("later question" != m["content"] for m in body["messages"])


async def test_unknown_and_oversized_token_404(env):
    client, _ = env
    async with client as c:
        assert (await c.get("/api/v1/public/shared/whatever")).status_code == 404
        assert (await c.get("/api/v1/public/shared/" + "x" * 40)).status_code == 404


async def test_unknown_conversation_404_on_enable(env):
    client, _ = env
    async with client as c:
        r = await c.post(f"/api/v1/conversations/{uuid.uuid4()}/share")
    assert r.status_code == 404


async def test_public_rate_limited(env):
    client, state = env
    cid = state["conv"].id
    shared = FakeRedis()  # one instance → the counter accumulates across requests
    async with client as c:
        client._transport.app.dependency_overrides[get_redis] = lambda: shared
        token = (await c.post(f"/api/v1/conversations/{cid}/share")).json()["token"]
        codes = [
            (await c.get(f"/api/v1/public/shared/{token}")).status_code
            for _ in range(62)
        ]
    assert 429 in codes
