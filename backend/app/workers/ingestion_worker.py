"""Document ingestion worker (CLAUDE.md §4.5, §10).

Polls SQS and runs each document through the pipeline:
``partition → chunk → vectorize → store``. Progress is written to the
``documents`` row **and** published to Redis (``doc_pipeline:{id}``) so the
Knowledge-Base modal can stream it live.

Dev: started in-process by the API lifespan (``settings.run_ingestion_worker``).
Prod: ``uv run python -m app.workers.ingestion_worker`` as a separate ECS service.
Idempotent — a re-delivered message for a ``ready`` document is a no-op.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog

from app.agents.rag import embedder
from app.config import settings
from app.core import aws
from app.core.logging import configure_logging
from app.core.redis import get_redis_client
from app.db.repositories.document_chunk_repo import DocumentChunkRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.project_repo import ProjectRepository
from app.db.session import get_sessionmaker
from app.schemas.rag import resolve as resolve_rag
from app.services.rag import chunk_service, partition_service

logger = structlog.get_logger(__name__)

_CHANNEL = "doc_pipeline:{}"


async def _publish(document_id: str, phase: str, status: str, stats: dict | None = None) -> None:
    try:
        await get_redis_client().publish(
            _CHANNEL.format(document_id),
            json.dumps({"phase": phase, "status": status, "stats": stats or {}}),
        )
    except Exception:  # noqa: BLE001 — progress is best-effort
        logger.debug("doc_publish_failed", document_id=document_id)


async def ingest_document(document_id: str) -> None:
    did = uuid.UUID(document_id)
    async with get_sessionmaker()() as db:
        repo = DocumentRepository(db)
        doc = await repo.get(did)
        if doc is None:
            logger.warning("ingest_document_missing", document_id=document_id)
            return
        if doc.status == "ready" or doc.processed_at is not None:
            logger.info("ingest_skip_done", document_id=document_id)
            return

        project = await ProjectRepository(db).get_for_user(doc.project_id, doc.user_id)
        rag = resolve_rag(project.rag_settings if project else None)
        log = logger.bind(document_id=document_id, kind=doc.kind)

        try:
            # 1. partition
            await repo.set_phase(did, "partition")
            await _publish(document_id, "partition", "processing")
            obj = aws.s3().get_object(Bucket=settings.S3_BUCKET_NAME, Key=doc.s3_key)
            data = obj["Body"].read()
            elements = partition_service.partition(doc.kind, data)
            el_stats = partition_service.element_stats(elements)
            await repo.set_phase(did, "chunk", stats_merge={"elements": el_stats})
            await _publish(document_id, "partition", "done", {"elements": el_stats})

            # 2. chunk
            await _publish(document_id, "chunk", "processing")
            chunks = chunk_service.chunk(
                elements, size=rag.chunk_size, overlap=rag.chunk_overlap
            )
            if not chunks:
                raise ValueError("no chunks produced")
            await repo.set_phase(did, "vectorize", stats_merge={"chunk_count": len(chunks)})
            await _publish(document_id, "chunk", "done", {"chunk_count": len(chunks)})

            # 3. vectorize
            await _publish(document_id, "vectorize", "processing")
            vectors = await embedder.embed_batch([c.text for c in chunks])
            await repo.set_phase(did, "store")
            await _publish(document_id, "vectorize", "done")

            # 4. store
            await _publish(document_id, "store", "processing")
            await DocumentChunkRepository(db).bulk_insert(
                [
                    {
                        "document_id": did,
                        "project_id": doc.project_id,
                        "user_id": doc.user_id,
                        "chunk_index": c.index,
                        "content": c.text,
                        "token_count": c.token_count,
                        "embedding": v,
                        "chunk_metadata": c.metadata,
                    }
                    for c, v in zip(chunks, vectors, strict=True)
                ]
            )
            await repo.mark_ready(
                did, {"elements": el_stats, "chunk_count": len(chunks)}
            )
            await _publish(
                document_id, "done", "ready", {"elements": el_stats, "chunk_count": len(chunks)}
            )
            log.info("ingest_done", chunks=len(chunks))
        except Exception as exc:  # noqa: BLE001
            log.exception("ingest_failed")
            await repo.set_phase(did, doc.phase, status="failed", error=str(exc)[:500])
            await _publish(document_id, doc.phase, "failed")


async def _handle(body: str, sem: asyncio.Semaphore, receipt: str) -> None:
    async with sem:
        try:
            msg = json.loads(body)
            if msg.get("job") == "ingest_document":
                await ingest_document(msg["document_id"])
        except Exception:  # noqa: BLE001 — never crash the loop
            logger.exception("ingest_message_failed", body=body[:200])
        finally:
            try:
                aws.sqs().delete_message(
                    QueueUrl=settings.SQS_QUEUE_URL, ReceiptHandle=receipt
                )
            except Exception:  # noqa: BLE001
                logger.debug("sqs_delete_failed")


async def poll_loop() -> None:
    if not settings.aws_configured:
        logger.warning("ingestion_worker_no_aws")
        return
    sem = asyncio.Semaphore(settings.INGESTION_CONCURRENCY)
    logger.info("ingestion_worker_running", concurrency=settings.INGESTION_CONCURRENCY)
    while True:
        try:
            resp = await asyncio.to_thread(
                aws.sqs().receive_message,
                QueueUrl=settings.SQS_QUEUE_URL,
                MaxNumberOfMessages=settings.INGESTION_CONCURRENCY,
                WaitTimeSeconds=20,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("sqs_receive_failed")
            await asyncio.sleep(5)
            continue
        for m in resp.get("Messages", []):
            asyncio.create_task(_handle(m["Body"], sem, m["ReceiptHandle"]))


async def main() -> None:
    configure_logging()
    aws.ensure_infra()
    await poll_loop()


if __name__ == "__main__":
    asyncio.run(main())
