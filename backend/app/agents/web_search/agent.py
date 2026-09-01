"""Web Search agent (CLAUDE.md §12).

Single responsibility: search the web (Tavily) and return a grounded summary with
sources. Never creates tasks, never writes to calendar. The summary is handed to
the synthesiser, which composes the final user-facing answer.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import AgentResult
from app.agents.models import ainvoke, get_chat_model
from app.agents.supervisor.state import GenieState, TaskRecord
from app.agents.web_search.prompts import WEB_SEARCH_SUMMARY_PROMPT
from app.agents.web_search.tools import extract_sources, format_results, tavily_search
from app.config import settings

logger = structlog.get_logger(__name__)


def _query_for(state: GenieState, task: TaskRecord) -> str:
    query = (task.get("description") or "").strip()
    if query:
        return query
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


async def run_web_search(state: GenieState, task: TaskRecord) -> AgentResult:
    if not settings.tavily_configured:
        logger.error("web_search_no_api_key")
        raise RuntimeError("web_search unavailable — TAVILY_API_KEY is not set")

    query = _query_for(state, task)
    logger.info("web_search_query", task_id=task.get("id"), query=query)
    data = await tavily_search(query)
    context = format_results(data)
    sources = extract_sources(data)

    logger.info(
        "web_search_results",
        query=query,
        result_count=len(sources),
        has_tavily_answer=bool((data or {}).get("answer")),
        context_chars=len(context),
        source_urls=[s.get("url") for s in sources],
    )

    if not settings.llm_configured:
        logger.info("web_search_no_llm", note="returning raw Tavily context")
        return AgentResult(
            summary=(data or {}).get("answer") or context[:1500],
            detail=context,
            sources=sources,
        )

    model = get_chat_model(streaming=False, temperature=0.2)
    prompt = WEB_SEARCH_SUMMARY_PROMPT.format(query=query, results=context)
    resp = await ainvoke(model, [SystemMessage(content=prompt), HumanMessage(content=query)])
    summary = str(resp.content).strip()
    logger.info("web_search_summarised", query=query, summary_chars=len(summary))
    return AgentResult(summary=summary, detail=context, sources=sources)
