"""Chat endpoints — two-step flow + SSE (CLAUDE.md §11, §14)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clerk import get_current_user
from app.core.redis import get_redis
from app.core.usage import enforce_token_limits
from app.db.models.user import User
from app.db.session import get_db
from app.memory import short_term
from app.services import chat_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    project_id: str | None = None  # start a new chat inside this project
    client_hour: int | None = None  # the user's local hour (0-23), for time-aware agents
    model: str | None = None  # picked chat-model id (MODEL_CATALOG); None → server default
    attachment_ids: list[str] | None = None  # files from POST /attachments, this turn only


class ChatAccepted(BaseModel):
    run_id: str
    conversation_id: str


@router.post("", response_model=ChatAccepted)
async def create_chat_run(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ChatAccepted:
    message = body.message.strip()
    if not message:
        logger.info("chat_post_empty_message", user_id=str(user.id))
        raise HTTPException(status_code=422, detail="message must not be empty")

    if not await short_term.check_rate_limit(
        redis, str(user.id), settings.RATE_LIMIT_REQUESTS_PER_MINUTE
    ):
        raise HTTPException(
            status_code=429,
            detail=f"rate limit: {settings.RATE_LIMIT_REQUESTS_PER_MINUTE} messages/minute",
        )
    await enforce_token_limits(db, user.id)

    try:
        run_id, conversation_id = await chat_service.create_turn(
            db,
            redis,
            user,
            message,
            body.conversation_id,
            body.project_id,
            body.client_hour,
            body.model,
            body.attachment_ids,
        )
    except ValueError as exc:
        logger.warning("chat_post_rejected", user_id=str(user.id), error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatAccepted(run_id=run_id, conversation_id=conversation_id)


class RegenerateRequest(BaseModel):
    from_message_id: str
    edit: str | None = None  # present → replace the (user) target's text first


@router.post("/{conversation_id}/regenerate", response_model=ChatAccepted)
async def regenerate_chat_run(
    conversation_id: str,
    body: RegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ChatAccepted:
    """Truncate the conversation at ``from_message_id`` and re-run from there —
    regenerate a Genie reply, or retry/edit one of the user's messages."""
    if not await short_term.check_rate_limit(
        redis, str(user.id), settings.RATE_LIMIT_REQUESTS_PER_MINUTE
    ):
        raise HTTPException(status_code=429, detail="rate limit")
    await enforce_token_limits(db, user.id)
    try:
        run_id, cid = await chat_service.regenerate_turn(
            db, redis, user, conversation_id, body.from_message_id, body.edit
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatAccepted(run_id=run_id, conversation_id=cid)


@router.get("/{conversation_id}/stream")
async def stream_chat(
    conversation_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """SSE stream — emits `token` frames then `done` (CLAUDE.md §11)."""
    logger.info(
        "chat_stream_opened",
        conversation_id=conversation_id,
        run_id=run_id,
        user_id=str(user.id),
    )
    return StreamingResponse(
        chat_service.stream_turn(db, redis, user, conversation_id, run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{conversation_id}/confirm")
async def confirm_interrupt(conversation_id: str, user: User = Depends(get_current_user)):
    """Resume a graph interrupted before a calendar write (Phase 3)."""
    raise HTTPException(status_code=501, detail="Interrupt confirm not implemented yet (Phase 3)")
