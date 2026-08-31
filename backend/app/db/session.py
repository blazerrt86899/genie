"""Async SQLAlchemy engine + session factory (CLAUDE.md §3).

FastAPI request handlers use ``DATABASE_URL_POOL`` (Supavisor transaction mode).
The LangGraph checkpointer uses ``DATABASE_URL_SESSION`` separately.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db.models.base import DB_SCHEMA

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Genie tables live in the `genie` schema; `extensions` is where Supabase keeps
# pgvector etc. Models are schema-qualified, but this keeps ad-hoc SQL sane too.
_SEARCH_PATH = f"{DB_SCHEMA},public,extensions"


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        logger.info(
            "db_engine_init",
            url=settings.DATABASE_URL_POOL,  # credentials scrubbed by the log processor
            search_path=_SEARCH_PATH,
            pool_size=5,
            max_overflow=10,
        )
        _engine = create_async_engine(
            settings.DATABASE_URL_POOL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
            connect_args={"server_settings": {"search_path": _SEARCH_PATH}},
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, rolls back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            logger.warning("db_session_rollback", reason="exception in request handler")
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("db_engine_disposed")
