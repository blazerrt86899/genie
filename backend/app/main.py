"""FastAPI application factory + lifespan (CLAUDE.md §15 Phase 1).

Run:  uv run uvicorn "app.main:create_app" --factory --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.redis import close_redis, get_redis_client
from app.db.session import dispose_engine, get_engine

logger = structlog.get_logger(__name__)


async def _setup_checkpointer() -> None:
    """Create the LangGraph checkpointer tables (CLAUDE.md §8.2).

    Never managed by Alembic. Uses the session-mode URL (psycopg, not asyncpg).
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn_string = settings.DATABASE_URL_SESSION.replace("+asyncpg", "")
    async with AsyncPostgresSaver.from_conn_string(conn_string) as checkpointer:
        await checkpointer.setup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("startup_begin", env=settings.APP_ENV)

    # Redis — required
    redis = get_redis_client()
    await redis.ping()
    logger.info("redis_connected")

    # Database — required
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("database_connected")

    # LangGraph checkpointer tables
    try:
        await _setup_checkpointer()
        logger.info("checkpointer_ready")
    except Exception as exc:  # noqa: BLE001
        if settings.is_production:
            raise
        logger.warning("checkpointer_setup_failed", error=str(exc))

    logger.info("startup_complete")
    yield

    await close_redis()
    await dispose_engine()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Genie API",
        version="0.1.0",
        description="Multi-agent AI orchestration platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> dict:
        checks: dict[str, str] = {}
        try:
            await get_redis_client().ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {exc}"
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {exc}"
        status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return {"status": status, "checks": checks}

    app.include_router(api_router)
    return app
