"""Structured JSON logging via structlog (CLAUDE.md §8.8, §17).

Never log passwords, tokens, or full message content.
"""

from __future__ import annotations

import logging

import structlog

from app.config import settings


def configure_logging() -> None:
    """Call once at application startup."""
    level = logging.INFO if settings.is_production else logging.DEBUG
    logging.basicConfig(format="%(message)s", level=level)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
