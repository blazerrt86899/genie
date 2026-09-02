"""Per-message actions (CLAUDE.md §14). Currently: 👍 / 👎 feedback."""

from __future__ import annotations

import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.core.observability import send_run_feedback
from app.db.models.user import User
from app.db.repositories.message_repo import MessageRepository
from app.db.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/messages", tags=["messages"])


class FeedbackRequest(BaseModel):
    vote: Literal["up", "down"] | None  # null clears the vote


class FeedbackOut(BaseModel):
    vote: str | None


@router.post("/{message_id}/feedback", response_model=FeedbackOut)
async def set_feedback(
    message_id: str,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackOut:
    try:
        mid = uuid.UUID(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="message not found") from exc

    msg = await MessageRepository(db).set_feedback(mid, user.id, body.vote)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")

    # best-effort — forward the thumbs to LangSmith for that turn's traced run
    run_id = (msg.message_metadata or {}).get("langsmith_run_id")
    if run_id and body.vote is not None:
        send_run_feedback(run_id, score=1.0 if body.vote == "up" else 0.0)

    return FeedbackOut(vote=body.vote)
