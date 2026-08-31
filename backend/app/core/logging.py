"""Structured logging via structlog (CLAUDE.md §8, §21).

Every module logs its steps through ``structlog.get_logger(__name__)``. Logs are
structured (key/value) — console-rendered in dev, JSON in prod (ready for the
Datadog agent to ship). A redaction processor scrubs secrets from EVERY event
before it is rendered, so it is safe to pass tokens / URLs / payloads as fields;
still, prefer ``preview()`` for user content and never log raw credentials on
purpose.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

from app.config import settings

# ─── Redaction ───────────────────────────────────────────────────────────────

# Field names whose value is always a secret (compared case-insensitively).
_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password", "passwd", "secret", "token", "jwt", "authorization", "auth",
        "bearer", "credentials", "credential", "cookie", "api_key", "apikey",
        "access_token", "refresh_token", "id_token", "session_token",
        "client_secret", "webhook_secret", "signing_secret", "signature",
        "svix_signature", "private_key", "secret_key", "signing_key",
        "openai_api_key", "anthropic_api_key", "tavily_api_key",
        "clerk_secret_key", "clerk_webhook_secret", "service_role_key",
        "anon_key", "aws_secret_access_key", "aws_access_key_id",
        "oauth_token_encryption_key", "encryption_key",
        "database_url", "database_url_pool", "database_url_direct",
        "database_url_session", "redis_url", "dsn", "conn_string",
    }
)
_SECRET_SUFFIXES: tuple[str, ...] = (
    "_token", "_secret", "_password", "_api_key", "_apikey", "_signature",
    "_credential", "_dsn",
)
# Value prefixes that betray a secret regardless of the field name.
_SECRET_VALUE_PREFIXES: tuple[str, ...] = ("bearer ", "sk_", "sk-", "whsec_", "eyj")

_URL_CREDS = re.compile(r"(?P<pre>[a-z][a-z0-9+.\-]*://[^:/@\s]+:)(?P<pw>[^@/\s]+)@")

_PLACEHOLDER = "«redacted»"


def _mask(value: Any) -> str:
    text = str(value)
    if len(text) <= 6:
        return _PLACEHOLDER
    return f"{text[:3]}…{text[-2:]} (len={len(text)})"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        if _URL_CREDS.search(value):
            return _URL_CREDS.sub(r"\g<pre>«redacted»@", value)
        if value[:5].lower().startswith(_SECRET_VALUE_PREFIXES):
            return _mask(value)
        return value
    if isinstance(value, dict):
        return {k: _scrub_kv(k, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub_value(v) for v in value)
    return value


def _scrub_kv(key: str, value: Any) -> Any:
    lk = str(key).lower()
    if lk in _SECRET_KEYS or lk.endswith(_SECRET_SUFFIXES):
        return _PLACEHOLDER if value in (None, "") else _mask(value)
    return _scrub_value(value)


def redact_processor(_logger: Any, _name: str, event_dict: dict) -> dict:
    """structlog processor — scrub secret fields from every log event."""
    for key in list(event_dict.keys()):
        event_dict[key] = _scrub_kv(key, event_dict[key])
    return event_dict


# ─── Helpers for call sites ──────────────────────────────────────────────────


def preview(text: Any, limit: int = 160) -> str:
    """A short, single-line preview of user content — never log it in full."""
    s = " ".join(str(text).split())
    return s if len(s) <= limit else f"{s[:limit]}… (+{len(s) - limit} chars)"


def mask(value: Any) -> str:
    """Explicitly mask a value at a call site (the processor also catches most)."""
    return _mask(value)


# ─── Configuration ───────────────────────────────────────────────────────────


# Third-party loggers that are far too chatty at DEBUG — pin them higher so our
# own DEBUG lines stay readable in dev.
_NOISY_LOGGERS: dict[str, int] = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "openai": logging.WARNING,
    "urllib3": logging.WARNING,
    "asyncio": logging.WARNING,
    "hpack": logging.WARNING,
    "watchfiles": logging.WARNING,
    "langsmith": logging.WARNING,
    "sqlalchemy.engine": logging.WARNING,
}


def configure_logging() -> None:
    """Call once at application startup."""
    level = logging.INFO if settings.is_production else logging.DEBUG
    logging.basicConfig(format="%(message)s", level=level)
    for name, lvl in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(lvl)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_processor,  # must run last, just before rendering
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
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
