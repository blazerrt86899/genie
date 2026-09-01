"""Attachment endpoints — the composer "+" menu file uploads (CLAUDE.md §14).

Upload is synchronous (text only, ≤ 5 MB). The returned ``id`` is sent back on
``POST /chat`` as ``attachment_ids``; the parsed text augments that one turn.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services import attachment_service
from app.services.attachment_service import AttachmentError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])


class AttachmentOut(BaseModel):
    id: str
    filename: str
    kind: str
    char_count: int
    token_estimate: int


@router.post("", response_model=AttachmentOut, status_code=201)
async def upload_attachment(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentOut:
    data = await file.read()
    logger.info(
        "attachment_upload_start",
        user_id=str(user.id),
        filename=file.filename,
        bytes=len(data),
    )
    try:
        att = await attachment_service.create_attachment(
            db, user.id, file.filename or "file", data
        )
    except AttachmentError as exc:
        logger.info("attachment_rejected", user_id=str(user.id), reason=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info("attachment_uploaded", attachment_id=str(att.id), kind=att.kind)
    return AttachmentOut(
        id=str(att.id),
        filename=att.filename,
        kind=att.kind,
        char_count=att.char_count,
        token_estimate=att.token_estimate,
    )


@router.delete("/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ok = await attachment_service.delete_attachment(db, user.id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="attachment not found")
    return Response(status_code=204)
