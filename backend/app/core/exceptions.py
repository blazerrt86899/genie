"""Custom exception classes + FastAPI handlers (CLAUDE.md §5)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class GenieError(Exception):
    """Base class for all application errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.__doc__ or "Error"
        super().__init__(self.message)


class NotFoundError(GenieError):
    """Requested resource was not found."""

    status_code = 404
    code = "not_found"


class AuthError(GenieError):
    """Authentication or authorization failed."""

    status_code = 401
    code = "auth_error"


class RateLimitError(GenieError):
    """Rate limit exceeded."""

    status_code = 429
    code = "rate_limited"


class TokenBudgetExceeded(GenieError):
    """LangGraph run exceeded its token ceiling (CLAUDE.md §4.6)."""

    status_code = 402
    code = "token_budget_exceeded"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GenieError)
    async def _handle_genie_error(_: Request, exc: GenieError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
