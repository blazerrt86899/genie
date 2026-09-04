"""Generated-file download endpoint (CLAUDE.md §14).

The only way a generated file's bytes leave the server — ownership-checked,
streamed straight from S3 with the right content type + filename.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services import file_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    try:
        fid = uuid.UUID(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="file not found") from exc

    result = await file_service.download_bytes(db, user.id, fid)
    if result is None:
        logger.info("generated_file_download_404", file_id=file_id, user_id=str(user.id))
        raise HTTPException(status_code=404, detail="file not found")
    row, data = result

    return StreamingResponse(
        iter([data]),
        media_type=row.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename}"'},
    )
