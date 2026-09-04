"""Token-usage windows + soft enforcement (Settings → Usage, CLAUDE.md §14).

Estimated reply tokens (`messages.metadata.total_tokens`, `chars/4` fallback) are
summed over a UTC calendar **day** and **ISO week** (Monday 00:00). When
``USAGE_LIMITS_ENFORCED`` and a window is exhausted, ``enforce_token_limits``
raises a 429 that ``POST /chat`` surfaces to the user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.repositories.message_repo import MessageRepository

logger = structlog.get_logger(__name__)


def window_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """`(day_start, week_start)` in UTC — the current calendar day and ISO week."""
    now = now or datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=now.weekday())  # Monday
    return day_start, week_start


def _reset_hint(resets_at: datetime) -> str:
    hours = max(1, round((resets_at - datetime.now(UTC)).total_seconds() / 3600))
    if hours <= 36:
        return f"resets in ~{hours}h"
    return f"resets {resets_at:%A}"


async def enforce_token_limits(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Raise 429 if the user has exhausted the daily or weekly token limit."""
    if not settings.USAGE_LIMITS_ENFORCED:
        return
    day_start, week_start = window_bounds()
    w = await MessageRepository(db).token_usage_windows(user_id, day_start, week_start)

    if w["weekly"] >= settings.WEEKLY_TOKEN_LIMIT:
        hint = _reset_hint(week_start + timedelta(days=7))
        logger.warning("usage_limit_block", user_id=str(user_id), window="weekly", used=w["weekly"])
        raise HTTPException(
            status_code=429,
            detail=f"Weekly token limit reached ({settings.WEEKLY_TOKEN_LIMIT:,}) — {hint}.",
        )
    if w["daily"] >= settings.DAILY_TOKEN_LIMIT:
        hint = _reset_hint(day_start + timedelta(days=1))
        logger.warning("usage_limit_block", user_id=str(user_id), window="daily", used=w["daily"])
        raise HTTPException(
            status_code=429,
            detail=f"Daily token limit reached ({settings.DAILY_TOKEN_LIMIT:,}) — {hint}.",
        )
