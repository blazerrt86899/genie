"""Greeting agent (CLAUDE.md §12).

Single responsibility: greet the user based on their local time of day. Every
greeting-type query is routed here by the supervisor. Never answers anything else.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import AgentResult
from app.agents.greeting.prompts import GREETING_SYSTEM_PROMPT, TEMPLATE_GREETINGS
from app.agents.models import ainvoke, get_utility_model
from app.agents.supervisor.state import GenieState, TaskRecord
from app.config import settings

logger = structlog.get_logger(__name__)


def part_of_day(hour: int) -> str:
    """Bucket an hour (0-23) into morning / afternoon / evening / night."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _last_user_text(state: GenieState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
        if getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


async def run_greeting(state: GenieState, task: TaskRecord) -> AgentResult:  # noqa: ARG001
    client_hour = state.get("client_hour")
    valid = client_hour is not None and 0 <= client_hour <= 23
    hour = client_hour if valid else datetime.now().hour
    bucket = part_of_day(hour)
    fallback = TEMPLATE_GREETINGS[bucket]
    logger.info(
        "greeting_start",
        client_hour=client_hour,
        resolved_hour=hour,
        part_of_day=bucket,
        llm=settings.llm_configured,
    )

    if not settings.llm_configured:
        logger.info("greeting_template_used", reason="llm_not_configured")
        return AgentResult(summary=fallback, stream=True)

    try:
        model = get_utility_model(temperature=0.7, max_tokens=80)
        system = GREETING_SYSTEM_PROMPT.format(part_of_day=bucket, hour=hour)
        user_text = _last_user_text(state) or "Hello"
        resp = await ainvoke(
            model, [SystemMessage(content=system), HumanMessage(content=user_text)]
        )
        text = str(resp.content).strip()
        logger.info("greeting_generated", chars=len(text), fell_back=not text)
        return AgentResult(summary=text or fallback, stream=True)
    except Exception:  # noqa: BLE001 — greeting must never break a turn
        logger.warning("greeting_llm_failed", part_of_day=bucket, exc_info=True)
        return AgentResult(summary=fallback, stream=True)
