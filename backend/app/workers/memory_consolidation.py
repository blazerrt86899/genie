"""Memory consolidation job handler — STUB (Phase 2/3).

1. check ``processed_at IS NULL``  2. LLM extract facts  3. embed
4. upsert to user_memory  5. mark ``memory_consolidated = true``
"""

from __future__ import annotations


async def handle(job: dict) -> None:
    raise NotImplementedError("Phase 2")


if __name__ == "__main__":
    print("memory_consolidation: TODO — not implemented yet")
