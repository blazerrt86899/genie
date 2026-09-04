"""Conversation endpoints (CLAUDE.md §14)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
    feedback: str | None = None  # "up" | "down" — the user's 👍/👎 on an assistant message
    cached: bool = False  # assistant reply served from the response cache
    guardrail: dict | None = None  # {redacted, flagged, message} — input scrub note (user msg)
    thinking: str | None = None  # the reasoning trace behind this message (assistant only)
    thinking_ms: int | None = None  # how long that reasoning took
    files: list[dict] = []  # generated files attached to this message (assistant only)


class ConversationPatch(BaseModel):
    project_id: str | None = None  # move into a project, or null to detach
    title: str | None = None  # rename
    pinned: bool | None = None  # pin / unpin
    unread: bool | None = None  # mark as unread / read


class ShareInfo(BaseModel):
    token: str
    url: str  # absolute — {FRONTEND_BASE_URL}/share/{token}
    shared_at: datetime


class ConversationDetail(ConversationSummary):
    project: ProjectRef | None
    messages: list[MessageOut]
    share: ShareInfo | None = None


def _share_info(c) -> ShareInfo | None:
    token = getattr(c, "share_token", None)
    if not token or getattr(c, "shared_at", None) is None:
        return None
    return ShareInfo(
        token=token,
        url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/share/{token}",
        shared_at=c.shared_at,
    )


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


class ConversationSearchResult(ConversationSummary):
    snippet: str | None = None  # excerpt of the first matching message (content match only)


# NB: declared before `/{conversation_id}` so "search" isn't parsed as an id.
@router.get("/search", response_model=list[ConversationSearchResult])
async def search_conversations(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(30, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSearchResult]:
    """Search the user's conversations by title **and** message content."""
    rows = await ConversationRepository(db).search(user.id, q.strip(), limit)
    return [
        ConversationSearchResult(**conversation_summary(c).model_dump(), snippet=s)
        for c, s in rows
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
        share=_share_info(conv),
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                agents=list((m.message_metadata or {}).get("agents", [])),
                attachments=list((m.message_metadata or {}).get("attachments", [])),
                sources=list((m.message_metadata or {}).get("sources", [])),
                feedback=(m.message_metadata or {}).get("feedback"),
                cached=bool((m.message_metadata or {}).get("cached")),
                guardrail=(m.message_metadata or {}).get("guardrail"),
                thinking=(m.message_metadata or {}).get("thinking"),
                thinking_ms=(m.message_metadata or {}).get("thinking_ms"),
                files=list((m.message_metadata or {}).get("files", [])),
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


async def _owned_conversation(conversation_id: str, user: User, db: AsyncSession):
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc
    conv = await ConversationRepository(db).get_for_user(cid, user.id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return cid, conv


@router.get("/{conversation_id}/share", response_model=ShareInfo | None)
async def get_conversation_share(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareInfo | None:
    _, conv = await _owned_conversation(conversation_id, user, db)
    return _share_info(conv)


@router.post("/{conversation_id}/share", response_model=ShareInfo)
async def enable_conversation_share(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareInfo:
    """Create the public link, or return the existing one unchanged (stable URL).
    The message cutoff (`shared_at`) is frozen at first share — disable then
    re-enable to rotate the token and move the cutoff forward."""
    cid, conv = await _owned_conversation(conversation_id, user, db)
    existing = _share_info(conv)
    if existing is not None:
        return existing

    repo = ConversationRepository(db)
    now = datetime.now(UTC)
    for _ in range(3):
        token = secrets.token_urlsafe(16)  # 22 chars, 128-bit
        try:
            await repo.set_share(cid, user.id, token, now)
            break
        except IntegrityError:  # token collision — vanishingly rare
            await db.rollback()
            logger.warning("share_token_collision", conversation_id=conversation_id)
    else:
        raise HTTPException(status_code=500, detail="could not allocate a share link")

    logger.info("conversation_share_enabled", conversation_id=conversation_id)
    return ShareInfo(
        token=token,
        url=f"{settings.FRONTEND_BASE_URL.rstrip('/')}/share/{token}",
        shared_at=now,
    )


@router.delete("/{conversation_id}/share", status_code=204)
async def disable_conversation_share(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    cid, _ = await _owned_conversation(conversation_id, user, db)
    await ConversationRepository(db).clear_share(cid, user.id)
    logger.info("conversation_share_disabled", conversation_id=conversation_id)
    return Response(status_code=204)


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
