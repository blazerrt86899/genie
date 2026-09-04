"""Clerk JWT verification on `GET /users/me` (CLAUDE.md §7.3, §16).

A throwaway RSA keypair stands in for Clerk's signing key; `_get_jwks` is
monkeypatched to serve the matching public JWK, and the repo/Redis are faked.
"""

from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
from app.core import clerk
from app.core.redis import get_redis
from app.db.session import get_db
from app.main import create_app
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm

_KID = "test-kid"
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks() -> dict:
    pub = json.loads(RSAAlgorithm.to_jwk(_PRIVATE_KEY.public_key()))
    pub.update({"kid": _KID, "use": "sig", "alg": "RS256"})
    return {"keys": [pub]}


def _token(sub: str = "user_test123", *, expired: bool = False) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "iat": now - 60, "exp": now - 30 if expired else now + 3600},
        _PRIVATE_KEY,
        algorithm="RS256",
        headers={"kid": _KID},
    )


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, k):
        return self.store.get(k)

    async def setex(self, k, _ttl, v):
        self.store[k] = v


class FakeUserRepo:
    created: list[str] = []

    def __init__(self, _db) -> None: ...

    async def get_by_id(self, _id):
        return None

    async def get_by_clerk_id(self, clerk_id):
        return None

    async def create_from_clerk_token(self, payload):
        FakeUserRepo.created.append(payload["sub"])
        return SimpleNamespace(
            id=uuid.uuid4(),
            email=f"{payload['sub']}@example.com",
            full_name="Test User",
            avatar_url=None,
            token_budget=100000,
        )

    async def touch_last_active(self, _id):
        return None


@pytest.fixture
def client(monkeypatch):
    FakeUserRepo.created = []
    monkeypatch.setattr(
        clerk,
        "settings",
        SimpleNamespace(
            clerk_configured=True,
            is_production=False,
            CLERK_USER_CACHE_TTL_SECONDS=300,
            JWKS_CACHE_TTL_SECONDS=3600,
        ),
    )
    monkeypatch.setattr(clerk, "UserRepository", FakeUserRepo)

    async def fake_get_jwks(_redis, *, force_refresh=False):
        return _jwks()

    monkeypatch.setattr(clerk, "_get_jwks", fake_get_jwks)

    fake_redis = FakeRedis()

    def _fake_db():
        yield None

    app = create_app()
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_redis] = lambda: fake_redis

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_valid_token_resolves_and_provisions(client):
    async with client as c:
        resp = await c.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {_token('user_abc')}"}
        )
    assert resp.status_code == 200
    body = resp.json()
    uuid.UUID(body["id"])  # a real internal uuid, not the dev id
    assert body["email"] == "user_abc@example.com"
    assert FakeUserRepo.created == ["user_abc"]


async def test_missing_token_is_401(client):
    async with client as c:
        resp = await c.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_expired_token_is_401(client):
    async with client as c:
        resp = await c.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {_token(expired=True)}"},
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token expired"


async def test_garbage_token_is_401(client):
    async with client as c:
        resp = await c.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
    assert resp.status_code == 401


async def test_usage(client, monkeypatch):
    from app.api.v1.endpoints import users as users_ep

    class FakeMsgRepo:
        def __init__(self, _db): ...

        async def token_usage_windows(self, user_id, day_start, week_start):
            return {"all_time": 23905, "daily": 6330, "weekly": 23503}

        async def usage_totals(self, user_id, since=None):
            return {"tokens": 23905, "messages": 137}

    class FakeConvRepo:
        def __init__(self, _db): ...

        async def count_for_user(self, user_id):
            return 21

    monkeypatch.setattr(users_ep, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(users_ep, "ConversationRepository", FakeConvRepo)

    async with client as c:
        resp = await c.get(
            "/api/v1/users/me/usage",
            headers={"Authorization": f"Bearer {_token('user_u1')}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["daily"]["used"] == 6330 and body["daily"]["limit"] == 100_000
    assert body["weekly"]["used"] == 23503 and body["weekly"]["limit"] == 700_000
    assert body["tokens_total"] == 23905
    assert body["messages"] == 137 and body["conversations"] == 21

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    assert now < datetime.fromisoformat(body["daily"]["resets_at"])
    assert now < datetime.fromisoformat(body["weekly"]["resets_at"])
