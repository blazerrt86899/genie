"""User endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.clerk import get_current_user
from app.db.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


class UserMe(BaseModel):
    id: str
    email: str
    full_name: str | None
    avatar_url: str | None
    token_budget: int


@router.get("/me", response_model=UserMe)
async def read_me(user: User = Depends(get_current_user)) -> UserMe:
    """Resolve the Clerk token to the internal user.

    The frontend calls this after sign-up and waits for 200 before redirecting
    to ``/chat`` (webhook race-condition guard — CLAUDE.md §7.8).
    """
    logger.info("users_me", user_id=str(user.id))
    return UserMe(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        token_budget=user.token_budget,
    )
