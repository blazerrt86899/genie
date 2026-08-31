"""Web Search tools — Tavily (CLAUDE.md §12).

Requires ``TAVILY_API_KEY``. ``tavily_search`` returns the raw Tavily response
``{"answer": str | None, "results": [{"title", "url", "content", "score"}, ...]}``.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from tavily import AsyncTavilyClient

from app.config import settings

logger = structlog.get_logger(__name__)


async def tavily_search(query: str, *, max_results: int = 5) -> dict[str, Any]:
    if not settings.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is not set")
    client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
    started = time.perf_counter()
    logger.info("tavily_request", query=query, max_results=max_results)
    try:
        resp = await client.search(
            query,
            max_results=max_results,
            search_depth="basic",
            include_answer=True,
        )
    except Exception:
        logger.exception("tavily_request_failed", query=query)
        raise
    logger.info(
        "tavily_response",
        query=query,
        results=len(resp.get("results", [])),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return resp


def format_results(data: dict[str, Any]) -> str:
    """Render Tavily results as a numbered context block for the LLM."""
    lines: list[str] = []
    answer = (data or {}).get("answer")
    if answer:
        lines.append(f"Tavily quick answer: {answer}\n")
    for i, r in enumerate((data or {}).get("results", []), start=1):
        lines.append(f"[{i}] {r.get('title', 'Untitled')} — {r.get('url', '')}")
        content = (r.get("content") or "").strip()
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines).strip() or "No results found."


def extract_sources(data: dict[str, Any]) -> list[dict]:
    return [
        {"title": r.get("title") or r.get("url") or "source", "url": r.get("url", "")}
        for r in (data or {}).get("results", [])
        if r.get("url")
    ]
