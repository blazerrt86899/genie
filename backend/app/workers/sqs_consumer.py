"""SQS consumer — STUB (Phase 3, CLAUDE.md §5).

Runs as a SEPARATE ECS service from the API. Polling loop dispatches by
``job_type``. Consumers MUST be idempotent (CLAUDE.md §4.5).
"""

from __future__ import annotations


async def poll_loop() -> None:
    raise NotImplementedError("Phase 3")


if __name__ == "__main__":
    print("sqs_consumer: TODO — not implemented yet")
