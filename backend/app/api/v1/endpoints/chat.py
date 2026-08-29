"""Chat endpoints — two-step flow + SSE (CLAUDE.md §11, §14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.core.redis import get_redis
from app.db.models.user import User
from app.db.session import get_db
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


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
        raise HTTPException(status_code=422, detail="message must not be empty")
    try:
        run_id, conversation_id = await chat_service.create_turn(
            db, redis, user, message, body.conversation_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatAccepted(run_id=run_id, conversation_id=conversation_id)


@router.get("/{conversation_id}/stream")
async def stream_chat(
    conversation_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """SSE stream — emits `token` frames then `done` (CLAUDE.md §11)."""
    return StreamingResponse(
        chat_service.stream_turn(db, redis, user, conversation_id, run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{conversation_id}/confirm")
async def confirm_interrupt(conversation_id: str, user: User = Depends(get_current_user)):
    """Resume a graph interrupted before a calendar write (Phase 3)."""
    raise HTTPException(status_code=501, detail="Interrupt confirm not implemented yet (Phase 3)")
