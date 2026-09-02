"""Conversation endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
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

logger = structlog.get_logger(__name__)

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
    model: str | None  # picked chat-model id (MODEL_CATALOG); None → server default
    pinned: bool = False
    unread: bool = False


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    agents: list[str] = []  # which agents produced this message (assistant only)
    attachments: list[dict] = []  # files sent with this message (user only)
    sources: list[dict] = []  # [{title, url}] cited by this message (assistant only)


class ConversationPatch(BaseModel):
    project_id: str | None = None  # move into a project, or null to detach
    title: str | None = None  # rename
    pinned: bool | None = None  # pin / unpin
    unread: bool | None = None  # mark as unread / read


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
        model=c.model,
        pinned=bool(getattr(c, "pinned", False)),
        unread=bool(getattr(c, "unread", False)),
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

    conv_repo = ConversationRepository(db)
    conv = await conv_repo.get_for_user(cid, user.id)
    if conv is None:
        logger.info("conversation_get_404", conversation_id=conversation_id, user_id=str(user.id))
        raise HTTPException(status_code=404, detail="conversation not found")

    if conv.unread:  # opening a chat marks it read
        await conv_repo.mark_read(cid, user.id)
        conv.unread = False

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
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                agents=list((m.message_metadata or {}).get("agents", [])),
                attachments=list((m.message_metadata or {}).get("attachments", [])),
                sources=list((m.message_metadata or {}).get("sources", [])),
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def patch_conversation(
    conversation_id: str,
    body: ConversationPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSummary:
    """Rename (``title``), pin/unpin (``pinned``), mark read/unread (``unread``),
    and/or move into a project (``project_id``, null = detach). Only the fields
    present in the body are touched."""
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc

    fields = body.model_dump(exclude_unset=True)
    conv_repo = ConversationRepository(db)
    conv = await conv_repo.get_for_user(cid, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    if "title" in fields:
        title = (fields["title"] or "").strip()
        if title:
            await conv_repo.set_title(cid, user.id, title[:255])

    flags = {k: bool(fields[k]) for k in ("pinned", "unread") if k in fields}
    if flags:
        await conv_repo.set_flag(cid, user.id, **flags)

    if "project_id" in fields:
        pid: uuid.UUID | None = None
        if fields["project_id"] is not None:
            try:
                pid = uuid.UUID(fields["project_id"])
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="project not found") from exc
            if await ProjectRepository(db).get_for_user(pid, user.id) is None:
                raise HTTPException(status_code=404, detail="project not found")
        await conv_repo.set_project(cid, user.id, pid)

    updated = await conv_repo.get_for_user(cid, user.id)
    return conversation_summary(updated)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ok = await chat_service.delete_conversation(db, user, conversation_id)
    if not ok:
        logger.info(
            "conversation_delete_404", conversation_id=conversation_id, user_id=str(user.id)
        )
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)
