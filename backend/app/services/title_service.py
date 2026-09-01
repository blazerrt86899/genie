"""Auto-generate a short conversation title from the opening exchange
(Claude-style chat headings). One cheap LLM call; never blocks a turn.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.models import ainvoke, get_utility_model
from app.config import settings

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You name chat threads. Given the first user message and the assistant's "
    "reply, respond with a 3-6 word title in Title Case. Plain text only — no "
    "quotes, no trailing punctuation, no preamble."
)


async def generate_title(user_msg: str, assistant_msg: str) -> str | None:
    if not settings.llm_configured:
        logger.debug("title_skip", reason="llm_not_configured")
        return None
    try:
        model = get_utility_model(temperature=0.2, max_tokens=24)
        resp = await ainvoke(
            model,
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(
                    content=f"User: {user_msg[:800]}\n\nAssistant: {assistant_msg[:800]}"
                ),
            ],
        )
        raw = str(resp.content).strip().strip("\"'").rstrip(".").strip()
        title = raw[:60] or None
        logger.info("title_generated", model=settings.utility_model_name, title=title)
        return title
    except Exception as exc:  # noqa: BLE001
        logger.warning("title_generation_failed", error=str(exc))
        return None
