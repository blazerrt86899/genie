"""Auto-generate a short conversation title from the opening exchange
(Claude-style chat headings). One cheap LLM call; never blocks a turn.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import settings

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You name chat threads. Given the first user message and the assistant's "
    "reply, respond with a 3-6 word title in Title Case. Plain text only — no "
    "quotes, no trailing punctuation, no preamble."
)


async def generate_title(user_msg: str, assistant_msg: str) -> str | None:
    if not settings.llm_configured:
        return None
    try:
        model = ChatOpenAI(
            model=settings.OPENAI_TITLE_MODEL,
            temperature=0.2,
            streaming=False,
            max_tokens=24,
            api_key=settings.OPENAI_API_KEY,
        )
        resp = await model.ainvoke(
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(
                    content=f"User: {user_msg[:800]}\n\nAssistant: {assistant_msg[:800]}"
                ),
            ]
        )
        raw = str(resp.content).strip().strip("\"'").rstrip(".").strip()
        return raw[:60] or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("title_generation_failed", error=str(exc))
        return None
