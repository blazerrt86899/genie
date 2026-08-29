"""Document ingestion job handler — STUB (Phase 2).

Idempotent: skip if the document is already ``ready`` / chunks exist.
"""

from __future__ import annotations


async def handle(job: dict) -> None:
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    print("document_ingestion: TODO — not implemented yet")
