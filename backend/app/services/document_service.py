"""Knowledge-Base document orchestration (CLAUDE.md §10, §14).

The one code path for the REST endpoints + tests. Upload is synchronous
(bytes → S3, the durable handoff); the ingestion pipeline runs in the worker.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import aws
from app.db.models.document import DOCUMENT_KINDS, Document
from app.db.repositories.document_chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository

logger = structlog.get_logger(__name__)


class DocumentError(ValueError):
    """A file couldn't be accepted."""


_KIND = {".pdf": "pdf", ".md": "md", ".txt": "txt"}


async def create_and_enqueue(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> Document:
    ext = Path(filename or "").suffix.lower()
    if ext not in _KIND or _KIND[ext] not in DOCUMENT_KINDS:
        raise DocumentError("unsupported file type — pdf, md or txt only")
    if len(data) > settings.DOCUMENT_MAX_MB * 1024 * 1024:
        raise DocumentError(f"file too large ({settings.DOCUMENT_MAX_MB} MB max)")
    if not settings.aws_configured:
        raise DocumentError("storage is not configured (S3_BUCKET_NAME / SQS_QUEUE_URL)")

    doc_id = uuid.uuid4()
    s3_key = f"{user_id}/{project_id}/{doc_id}/{filename}"
    aws.s3().put_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=data)

    repo = DocumentRepository(db)
    doc = Document(
        id=doc_id,
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        kind=_KIND[ext],
        s3_key=s3_key,
        byte_size=len(data),
        status="queued",
        phase="upload",
    )
    doc = await repo.add(doc)

    aws.sqs().send_message(
        QueueUrl=settings.SQS_QUEUE_URL,
        MessageBody=json.dumps({"job": "ingest_document", "document_id": str(doc_id)}),
    )
    logger.info(
        "document_uploaded",
        document_id=str(doc_id),
        project_id=str(project_id),
        kind=doc.kind,
        bytes=len(data),
        s3_key=s3_key,
    )
    return doc


async def list_for_project(
    db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[Document]:
    return await DocumentRepository(db).list_for_project(project_id, user_id)


async def get(db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    return await DocumentRepository(db).get_for_user(document_id, user_id)


async def list_chunks(
    db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID, *, limit: int, offset: int
) -> list[dict]:
    rows = await DocumentChunkRepository(db).list_for_document(
        document_id, user_id, limit=limit, offset=offset
    )
    return [
        {
            "chunk_index": r.chunk_index,
            "content": r.content,
            "token_count": r.token_count,
            "metadata": r.chunk_metadata,
        }
        for r in rows
    ]


async def delete(db: AsyncSession, user_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    repo = DocumentRepository(db)
    doc = await repo.get_for_user(document_id, user_id)
    if doc is None:
        return False
    try:
        aws.s3().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=doc.s3_key)
    except Exception as exc:  # noqa: BLE001 — an orphan S3 object is harmless
        logger.warning("document_s3_delete_failed", document_id=str(document_id), error=str(exc))
    return await repo.delete_for_user(document_id, user_id)
