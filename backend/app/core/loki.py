"""Best-effort log shipper to a local Loki instance (CLAUDE.md §21).

Backs the "local log explorer" — `docker compose up -d loki grafana` then set
``LOKI_URL``. A thread-safe queue + one daemon background thread; a structlog
processor (`core/logging.py:_ship_to_loki`) enqueues every event and returns
immediately — request handling is never blocked or slowed by log shipping, and
a Loki outage is swallowed (throttled to one print every 30s) rather than
raised back into the app or spamming stdout.

No API key: the local Loki container (docker-compose) is unauthenticated.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any

import httpx

from app.config import settings

_LOKI_PATH = "/loki/api/v1/push"

_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
_thread: threading.Thread | None = None
_stop = threading.Event()
_last_error_logged = 0.0


def _labels() -> dict[str, str]:
    return {
        "service": "genie-backend",
        "env": "production" if settings.is_production else "development",
    }


def enqueue(event_dict: dict[str, Any]) -> None:
    """Queue one (already-redacted) log event for shipping. No-op unless
    ``LOKI_URL`` is set; drops (never blocks) if the queue is saturated —
    losing a burst of logs during an outage beats stalling the app."""
    if not settings.LOKI_URL:
        return
    try:
        _queue.put_nowait(dict(event_dict))
    except queue.Full:
        pass


def _log_push_failure(exc: Exception) -> None:
    global _last_error_logged
    now = time.monotonic()
    if now - _last_error_logged > 30:  # throttle — a Loki outage must not spam
        _last_error_logged = now
        # Not structlog — that would re-enter this very pipeline.
        print(f"loki_push_failed: {settings.LOKI_URL} — {exc}")  # noqa: T201


def _flush(client: httpx.Client, batch: list[dict[str, Any]]) -> None:
    """POST one batch, grouped into a Loki stream per level (low-cardinality
    labels only — everything else stays in the JSON line body, filterable via
    LogQL's `| json`)."""
    if not batch:
        return
    by_level: dict[str, list[dict[str, Any]]] = {}
    for event in batch:
        by_level.setdefault(str(event.get("level", "info")), []).append(event)

    streams = [
        {
            "stream": {**_labels(), "level": level},
            "values": [[str(time.time_ns()), json.dumps(e, default=str)] for e in events],
        }
        for level, events in by_level.items()
    ]

    try:
        resp = client.post(
            f"{settings.LOKI_URL}{_LOKI_PATH}", json={"streams": streams}, timeout=5.0
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — logging must never break the app
        _log_push_failure(exc)


def _worker() -> None:
    client = httpx.Client()
    try:
        while not _stop.is_set():
            batch: list[dict[str, Any]] = []
            deadline = time.monotonic() + settings.LOKI_FLUSH_INTERVAL_SECONDS
            while len(batch) < settings.LOKI_BATCH_SIZE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(_queue.get(timeout=remaining))
                except queue.Empty:
                    break
            _flush(client, batch)

        # Drain whatever is left so a clean shutdown doesn't lose the tail.
        remainder: list[dict[str, Any]] = []
        while True:
            try:
                remainder.append(_queue.get_nowait())
            except queue.Empty:
                break
        _flush(client, remainder)
    finally:
        client.close()


def start() -> None:
    """Start the background shipper thread. No-op if unconfigured or already
    running — called from `core/logging.py:configure_logging()`."""
    global _thread
    if not settings.LOKI_URL or _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_worker, name="loki-log-shipper", daemon=True)
    _thread.start()


def stop() -> None:
    """Flush the remaining queue and join the thread — called from
    `core/logging.py:shutdown_logging()` (the FastAPI lifespan's teardown)."""
    global _thread
    if _thread is None:
        return
    _stop.set()
    _thread.join(timeout=5.0)
    _thread = None
