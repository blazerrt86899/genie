"""FastAPI application factory + lifespan (CLAUDE.md §15 Phase 1).

Run:  uv run uvicorn "app.main:create_app" --factory --reload
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.agents.supervisor.graph import build_chat_graph, set_runtime_graph
from app.api.v1.router import api_router
from app.config import settings
from app.core.clerk import DEV_CLERK_ID, DEV_USER_ID
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.observability import configure_tracing
from app.core.redis import close_redis, get_redis_client
from app.db.models.base import DB_SCHEMA
from app.db.session import dispose_engine, get_engine

logger = structlog.get_logger(__name__)


def _checkpointer_conn_string() -> str:
    """Session-mode URL for psycopg, pinned to the genie schema so the LangGraph
    checkpointer tables land there too (it creates them unqualified)."""
    url = settings.DATABASE_URL_SESSION.replace("+asyncpg", "")
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}options=-csearch_path%3D{DB_SCHEMA}%2Cpublic"


async def _seed_dev_user() -> None:
    """Insert the fixed dev user so message/conversation FKs resolve while Clerk
    JWT verification is not yet wired (CLAUDE.md §7 dev bypass)."""
    async with get_engine().begin() as conn:
        await conn.execute(
            text(
                f"INSERT INTO {DB_SCHEMA}.users "
                "(id, clerk_id, email, full_name, email_verified, token_budget, metadata) "
                "VALUES (:id, :clerk_id, :email, 'Local Dev', true, 1000000, '{}'::jsonb) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": DEV_USER_ID, "clerk_id": DEV_CLERK_ID, "email": "dev@genie.local"},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_tracing()  # must run before the graph is compiled / any chain runs
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

    if not settings.clerk_configured and not settings.is_production:
        await _seed_dev_user()
        logger.info("dev_user_seeded")

    # LangGraph checkpointer + compiled chat graph — held for the app lifetime.
    # Session-mode URL, psycopg (not asyncpg). Single connection is fine for now.
    async with AsyncExitStack() as stack:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            checkpointer = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(_checkpointer_conn_string())
            )
            await checkpointer.setup()
            set_runtime_graph(build_chat_graph().compile(checkpointer=checkpointer))
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
