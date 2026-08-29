"""Document endpoints (CLAUDE.md §14). STUB (Phase 2).

Upload -> S3 -> SQS ingestion job -> 202 Accepted (never ingest synchronously).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.core.clerk import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=202)
async def upload_document(file: UploadFile, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.get("")
async def list_documents(user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: str, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")
