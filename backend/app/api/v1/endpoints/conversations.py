"""Conversation endpoints (CLAUDE.md §14). STUB (Phase 1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.clerk import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 1)")


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 1)")


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 1)")
