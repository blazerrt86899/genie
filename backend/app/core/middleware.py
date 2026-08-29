"""HTTP middleware: request_id injection + request timing (CLAUDE.md §8.8)."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "x-request-id"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request_id to every request and log timing."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request_completed",
                method=request.method,
                duration_ms=elapsed_ms,
            )
            structlog.contextvars.clear_contextvars()

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
