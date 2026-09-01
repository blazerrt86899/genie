"""Knowledge-Base document endpoints (CLAUDE.md §14).

Upload → S3 → SQS (the ingestion worker takes it from there). ``/stream`` relays
the worker's Redis progress so the pipeline modal updates live.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.core.redis import get_redis
from app.db.models.user import User
from app.db.repositories.document_chunk_repo import DocumentChunkRepository
from app.db.repositories.project_repo import ProjectRepository
from app.db.session import get_db
from app.services import document_service
from app.services.document_service import DocumentError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _sse(event: str, **data) -> str:
    return f"data: {json.dumps({'type': event, **data}, default=str)}\n\n"


class DocumentOut(BaseModel):
    id: str
    project_id: str
    filename: str
    kind: str
    status: str
    phase: str
    error: str | None
    stats: dict
    chunk_count: int
    byte_size: int
    created_at: datetime
    processed_at: datetime | None


class ChunkOut(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    metadata: dict


async def _out(db: AsyncSession, doc) -> DocumentOut:
    n = await DocumentChunkRepository(db).count_for_document(doc.id)
    return DocumentOut(
        id=str(doc.id),
        project_id=str(doc.project_id),
        filename=doc.filename,
        kind=doc.kind,
        status=doc.status,
        phase=doc.phase,
        error=doc.error,
        stats=doc.stats or {},
        chunk_count=n,
        byte_size=doc.byte_size,
        created_at=doc.created_at,
        processed_at=doc.processed_at,
    )


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"{what} not found") from exc


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    pid = _uuid(project_id, "project")
    if await ProjectRepository(db).get_for_user(pid, user.id) is None:
        raise HTTPException(status_code=404, detail="project not found")

    data = await file.read()
    try:
        doc = await document_service.create_and_enqueue(
            db, user.id, pid, file.filename or "file", data
        )
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _out(db, doc)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentOut]:
    pid = _uuid(project_id, "project")
    docs = await document_service.list_for_project(db, user.id, pid)
    return [await _out(db, d) for d in docs]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentOut:
    doc = await document_service.get(db, user.id, _uuid(document_id, "document"))
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return await _out(db, doc)


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    document_id: str,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChunkOut]:
    did = _uuid(document_id, "document")
    if await document_service.get(db, user.id, did) is None:
        raise HTTPException(status_code=404, detail="document not found")
    rows = await document_service.list_chunks(
        db, user.id, did, limit=min(limit, 200), offset=offset
    )
    return [ChunkOut(**r) for r in rows]


@router.get("/{document_id}/stream")
async def stream_pipeline(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    """SSE — relays the worker's ``doc_pipeline:{id}`` channel until done/failed."""
    did = _uuid(document_id, "document")
    doc = await document_service.get(db, user.id, did)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")

    async def gen():
        # emit the current state immediately (in case the worker already advanced)
        yield _sse("phase", phase=doc.phase, status=doc.status, stats=doc.stats or {})
        if doc.status in ("ready", "failed"):
            yield _sse("done", status=doc.status)
            return
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"doc_pipeline:{document_id}")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
                if msg is None:
                    yield ": keep-alive\n\n"
                    continue
                payload = json.loads(msg["data"])
                yield _sse("phase", **payload)
                if payload.get("status") in ("ready", "failed"):
                    yield _sse("done", status=payload["status"])
                    return
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(f"doc_pipeline:{document_id}")
            await pubsub.aclose()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    ok = await document_service.delete(db, user.id, _uuid(document_id, "document"))
    if not ok:
        raise HTTPException(status_code=404, detail="document not found")
    return Response(status_code=204)
