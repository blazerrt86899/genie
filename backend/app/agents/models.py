"""Shared LLM factories (CLAUDE.md §3 — always pin the model version)."""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI

from app.config import settings

logger = structlog.get_logger(__name__)


def get_chat_model(*, streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """The main chat model — used by the synthesiser and the agents."""
    logger.debug(
        "llm_model_build",
        model=settings.OPENAI_CHAT_MODEL,
        streaming=streaming,
        temperature=temperature,
    )
    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        temperature=temperature,
        streaming=streaming,
        api_key=settings.OPENAI_API_KEY,
    )


def get_utility_model(*, temperature: float = 0.4, max_tokens: int | None = None) -> ChatOpenAI:
    """A cheap model for small, non-streamed jobs (routing, greetings, titles)."""
    logger.debug(
        "llm_utility_model_build", model=settings.OPENAI_TITLE_MODEL, max_tokens=max_tokens
    )
    return ChatOpenAI(
        model=settings.OPENAI_TITLE_MODEL,
        temperature=temperature,
        streaming=False,
        max_tokens=max_tokens,
        api_key=settings.OPENAI_API_KEY,
    )
