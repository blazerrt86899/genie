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
from app.db.repositories.project_repo import ProjectRepository
from app.db.session import get_db
from app.services import chat_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ProjectRef(BaseModel):
    id: str
    name: str


class ConversationSummary(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    last_message_at: datetime | None
    project_id: str | None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetail(ConversationSummary):
    project: ProjectRef | None
    messages: list[MessageOut]


def conversation_summary(c) -> ConversationSummary:
    return ConversationSummary(
        id=str(c.id),
        title=c.title,
        created_at=c.created_at,
        last_message_at=c.last_message_at,
        project_id=str(c.project_id) if c.project_id else None,
    )


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    rows = await ConversationRepository(db).list_for_user(user.id)
    return [conversation_summary(c) for c in rows]


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

    project_ref: ProjectRef | None = None
    if conv.project_id is not None:
        project = await ProjectRepository(db).get_for_user(conv.project_id, user.id)
        if project is not None:
            project_ref = ProjectRef(id=str(project.id), name=project.name)

    messages = await MessageRepository(db).list_for_conversation(cid)
    return ConversationDetail(
        **conversation_summary(conv).model_dump(),
        project=project_ref,
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
