"""Unauthenticated public endpoints (CLAUDE.md §14).

Only shared-conversation reads live here. Every response is a deliberately
narrow whitelist — never `user_id`, email, project, model, or raw
`message_metadata`. Reachable only with the 128-bit `share_token`; IP
rate-limited to blunt scraping.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.session import get_db
from app.memory import short_term

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

_MAX_TOKEN_LEN = 24
_MAX_MESSAGES = 500
_RATE_PER_MIN = 60


class PublicMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    agents: list[str] = []
    sources: list[dict] = []
    attachments: list[dict] = []  # [{filename, kind}] only


class SharedConversationOut(BaseModel):
    title: str | None
    shared_at: datetime
    message_count: int
    messages: list[PublicMessage]


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/shared/{token}", response_model=SharedConversationOut)
async def get_shared_conversation(
    token: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> SharedConversationOut:
    ip = _client_ip(request)
    if not await short_term.check_rate_limit(redis, f"share_ip:{ip}", _RATE_PER_MIN):
        raise HTTPException(status_code=429, detail="rate limit")

    if not token or len(token) > _MAX_TOKEN_LEN:
        raise HTTPException(status_code=404, detail="not found")

    conv = await ConversationRepository(db).get_by_share_token(token)
    if conv is None or not conv.share_token or conv.shared_at is None:
        raise HTTPException(status_code=404, detail="not found")

    cutoff = conv.shared_at
    rows = await MessageRepository(db).list_for_conversation(conv.id, limit=_MAX_MESSAGES)
    visible = [m for m in rows if m.created_at <= cutoff]

    messages = [
        PublicMessage(
            id=str(m.id),
            role=m.role,
            content=m.content,
            created_at=m.created_at,
            agents=list((m.message_metadata or {}).get("agents", [])),
            sources=list((m.message_metadata or {}).get("sources", [])),
            attachments=[
                {"filename": a.get("filename"), "kind": a.get("kind")}
                for a in (m.message_metadata or {}).get("attachments", [])
            ],
        )
        for m in visible
    ]

    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    logger.info(
        "shared_view_served",
        token_prefix=token[:6],
        message_count=len(messages),
        ip=ip,
    )
    return SharedConversationOut(
        title=conv.title,
        shared_at=cutoff,
        message_count=len(messages),
        messages=messages,
    )
