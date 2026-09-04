"""core/usage.py — daily/weekly token-limit enforcement."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.core import usage
from fastapi import HTTPException


class FakeMsgRepo:
    def __init__(self, _db) -> None: ...

    windows = {"all_time": 0, "daily": 0, "weekly": 0}

    async def token_usage_windows(self, user_id, day_start, week_start):
        return FakeMsgRepo.windows


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(usage, "MessageRepository", FakeMsgRepo)
    monkeypatch.setattr(
        usage,
        "settings",
        SimpleNamespace(
            USAGE_LIMITS_ENFORCED=True,
            DAILY_TOKEN_LIMIT=100_000,
            WEEKLY_TOKEN_LIMIT=700_000,
        ),
    )


async def test_under_limit_passes():
    FakeMsgRepo.windows = {"all_time": 5, "daily": 5_000, "weekly": 40_000}
    await usage.enforce_token_limits(None, uuid.uuid4())  # no raise


async def test_daily_exceeded_blocks():
    FakeMsgRepo.windows = {"all_time": 0, "daily": 100_000, "weekly": 100_000}
    with pytest.raises(HTTPException) as ei:
        await usage.enforce_token_limits(None, uuid.uuid4())
    assert ei.value.status_code == 429
    assert "Daily token limit" in ei.value.detail


async def test_weekly_exceeded_blocks_first():
    FakeMsgRepo.windows = {"all_time": 0, "daily": 100_000, "weekly": 700_000}
    with pytest.raises(HTTPException) as ei:
        await usage.enforce_token_limits(None, uuid.uuid4())
    assert "Weekly token limit" in ei.value.detail


async def test_disabled_never_blocks(monkeypatch):
    monkeypatch.setattr(
        usage, "settings", SimpleNamespace(USAGE_LIMITS_ENFORCED=False)
    )
    FakeMsgRepo.windows = {"all_time": 0, "daily": 999_999, "weekly": 999_999}
    await usage.enforce_token_limits(None, uuid.uuid4())  # no raise
