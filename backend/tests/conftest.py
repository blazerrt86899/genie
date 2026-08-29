"""Shared pytest fixtures.

The health smoke test uses a transport-only client and does NOT trigger the
lifespan (no Redis/DB needed). Integration tests that need infra should spin up
the docker-compose stack.
"""

from __future__ import annotations

import pytest
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
