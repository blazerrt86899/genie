"""Conversation endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.session import get_db
from app.services import chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    last_message_at: datetime | None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut]


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    rows = await ConversationRepository(db).list_for_user(user.id)
    return [
        ConversationSummary(
            id=str(c.id),
            title=c.title,
            created_at=c.created_at,
            last_message_at=c.last_message_at,
        )
        for c in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc

    conv = await ConversationRepository(db).get_for_user(cid, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    messages = await MessageRepository(db).list_for_conversation(cid)
    return ConversationDetail(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at,
        last_message_at=conv.last_message_at,
        messages=[
            MessageOut(id=str(m.id), role=m.role, content=m.content, created_at=m.created_at)
            for m in messages
        ],
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ok = await chat_service.delete_conversation(db, user, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)
