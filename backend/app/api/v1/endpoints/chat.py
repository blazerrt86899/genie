"""Chat endpoints — two-step flow + SSE (CLAUDE.md §11, §14). STUB (Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.clerk import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatAccepted(BaseModel):
    run_id: str
    conversation_id: str


@router.post("", response_model=ChatAccepted)
async def create_chat_run(
    body: ChatRequest, user: User = Depends(get_current_user)
) -> ChatAccepted:
    raise HTTPException(status_code=501, detail="Chat run not implemented yet (Phase 1)")


@router.get("/{conversation_id}/stream")
async def stream_chat(conversation_id: str, run_id: str, user: User = Depends(get_current_user)):
    """SSE stream. Emits agent_start / token / agent_end / done (CLAUDE.md §11)."""
    raise HTTPException(status_code=501, detail="Chat stream not implemented yet (Phase 1)")


@router.post("/{conversation_id}/confirm")
async def confirm_interrupt(conversation_id: str, user: User = Depends(get_current_user)):
    """Resume a graph interrupted before a calendar write (Phase 3)."""
    raise HTTPException(status_code=501, detail="Interrupt confirm not implemented yet (Phase 3)")
