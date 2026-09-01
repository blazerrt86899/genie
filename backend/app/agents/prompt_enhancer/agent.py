"""Prompt Enhancer node (CLAUDE.md §9, §12).

Runs first, before the supervisor: rewrites the user's latest message into a
self-contained request and extracts an ``intent`` label. It is a graph node
(always runs), NOT a registry agent — it produces no user-facing output.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.events import emit
from app.agents.models import ainvoke, bump_tokens, get_utility_model, tokens_of
from app.agents.prompt_enhancer.prompts import PROMPT_ENHANCER_SYSTEM_PROMPT
from app.agents.supervisor.state import EnhancedPrompt, GenieState
from app.config import settings

logger = structlog.get_logger(__name__)


def _last_user_text(state: GenieState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


async def prompt_enhancer_node(state: GenieState) -> dict:
    original = _last_user_text(state)
    if not settings.llm_configured or not original.strip():
        return {"intent": "unknown", "enhanced_query": original or None}

    await emit("agent_start", {"agent": "prompt_enhancer", "task": "Understanding your request"})
    try:
        from app.agents.supervisor.nodes import _attachment_note

        model = get_utility_model(temperature=0).with_structured_output(
            EnhancedPrompt, include_raw=True
        )
        system = PROMPT_ENHANCER_SYSTEM_PROMPT + _attachment_note(state)
        result = await ainvoke(
            model, [SystemMessage(content=system), *state["messages"]]
        )
        parsed: EnhancedPrompt = result["parsed"]
        intent = parsed.intent.strip() or "unknown"
        enhanced = parsed.enhanced_query.strip() or original
        logger.info(
            "prompt_enhanced",
            intent=intent,
            rewritten=enhanced != original.strip(),
            needs_documents=parsed.needs_documents,
        )
        return {
            "intent": intent,
            "enhanced_query": enhanced,
            "needs_documents": bool(parsed.needs_documents),
            "token_usage": bump_tokens(
                state.get("token_usage"), tokens_of(result), "prompt_enhancer"
            ),
        }
    except Exception:  # noqa: BLE001 — never block the turn on enhancement
        logger.warning("prompt_enhance_failed", exc_info=True)
        # be safe: if we can't tell, allow retrieval (the retriever still gates on has_kb)
        return {"intent": "unknown", "enhanced_query": original, "needs_documents": True}
    finally:
        await emit("agent_end", {"agent": "prompt_enhancer", "status": "done"})
