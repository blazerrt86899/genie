"""Custom-event helper for agents (CLAUDE.md §11).

``emit(name, data)`` dispatches a LangChain custom event that surfaces in
``graph.astream_events`` as ``on_custom_event`` and is forwarded to the client
as SSE by ``chat_service``. Swallows the error when there is no callback manager
(e.g. a unit test calling an agent directly).
"""

from __future__ import annotations

import structlog
from langchain_core.callbacks import adispatch_custom_event

logger = structlog.get_logger("app.agents.events")


async def emit(name: str, data: dict) -> None:
    try:
        await adispatch_custom_event(name, data)
    except Exception:  # noqa: BLE001
        logger.debug("custom_event_not_dispatched", event_name=name)
