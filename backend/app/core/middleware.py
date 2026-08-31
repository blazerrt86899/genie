"""HTTP middleware: request_id injection + request timing (CLAUDE.md §8, §21)."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"

# Paths we don't want a log line for on every poll.
_QUIET_PATHS = frozenset({"/health", "/health/ready"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request_id to every request and log its lifecycle."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        path = request.url.path
        structlog.contextvars.bind_contextvars(request_id=request_id, path=path)
        request.state.request_id = request_id

        quiet = path in _QUIET_PATHS
        if not quiet:
            logger.info(
                "request_started",
                method=request.method,
                query=str(request.url.query) or None,
                client=request.client.host if request.client else None,
            )

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            logger.exception(
                "request_failed",
                method=request.method,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
            raise
        else:
            if not quiet:
                logger.info(
                    "request_completed",
                    method=request.method,
                    status_code=status_code,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
            structlog.contextvars.clear_contextvars()

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
