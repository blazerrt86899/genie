"""Shared LLM factories (CLAUDE.md §3 — always pin the model version)."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import settings


def get_chat_model(*, streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """The main chat model — used by the synthesiser and the agents."""
    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        temperature=temperature,
        streaming=streaming,
        api_key=settings.OPENAI_API_KEY,
    )


def get_utility_model(*, temperature: float = 0.4, max_tokens: int | None = None) -> ChatOpenAI:
    """A cheap model for small, non-streamed jobs (routing, greetings, titles)."""
    return ChatOpenAI(
        model=settings.OPENAI_TITLE_MODEL,
        temperature=temperature,
        streaming=False,
        max_tokens=max_tokens,
        api_key=settings.OPENAI_API_KEY,
    )
