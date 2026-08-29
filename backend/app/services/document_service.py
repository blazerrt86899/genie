"""Document ingestion — STUB (Phase 2, CLAUDE.md §15).

PDF/text -> chunks (512 tokens, 50 overlap) -> embed -> upsert to document_chunks.
"""

from __future__ import annotations


async def ingest_document(document_id: str) -> None:
    raise NotImplementedError("Phase 2")
