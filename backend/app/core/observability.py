"""LangSmith tracing wiring (CLAUDE.md §8).

LangChain / LangGraph decide whether to trace by reading ``os.environ`` at
runtime — but our config is loaded into a pydantic ``Settings`` object, which
never touches ``os.environ``. So we push the values across explicitly, once, at
startup (before the graph is compiled or any chain runs).
"""

from __future__ import annotations

import os

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)


def configure_tracing() -> None:
    if not settings.langsmith_enabled:
        logger.info(
            "langsmith_tracing_disabled",
            reason="LANGSMITH_TRACING is off or LANGSMITH_API_KEY is missing",
        )
        return

    env = {
        "LANGSMITH_TRACING": "true",
        "LANGCHAIN_TRACING_V2": "true",  # legacy readers
        "LANGSMITH_API_KEY": settings.LANGSMITH_API_KEY or "",
        "LANGCHAIN_API_KEY": settings.LANGSMITH_API_KEY or "",
        "LANGSMITH_ENDPOINT": settings.LANGSMITH_ENDPOINT,
        "LANGCHAIN_ENDPOINT": settings.LANGSMITH_ENDPOINT,
        "LANGSMITH_PROJECT": settings.LANGSMITH_PROJECT,
        "LANGCHAIN_PROJECT": settings.LANGSMITH_PROJECT,
    }
    os.environ.update(env)

    logger.info(
        "langsmith_tracing_enabled",
        project=settings.LANGSMITH_PROJECT,
        endpoint=settings.LANGSMITH_ENDPOINT,
    )


def send_run_feedback(run_id: str, score: float, comment: str | None = None) -> bool:
    """Best-effort — record a 👍/👎 against a traced run. No-op (and never raises)
    if LangSmith isn't configured or the client isn't importable."""
    if not run_id or not settings.langsmith_enabled:
        return False
    try:
        from langsmith import Client

        Client().create_feedback(
            run_id, key="user_thumbs", score=score, comment=comment
        )
        logger.info("message_feedback_langsmith", run_id=run_id, score=score)
        return True
    except Exception:  # noqa: BLE001 — telemetry must never break the request
        logger.warning("message_feedback_langsmith_failed", run_id=run_id, exc_info=True)
        return False
