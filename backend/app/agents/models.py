"""Shared LLM factories + a retrying ``ainvoke`` (CLAUDE.md §3, §4).

Every LLM call in the agent graph goes through ``ainvoke()`` so it gets the same
3-attempt exponential backoff on transient OpenAI errors (rate limit, timeout,
connection, 5xx). ``tokens_of()`` pulls the token count off a response so nodes
can accumulate ``GenieState['token_usage']`` (the supervisor's budget guard).
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = structlog.get_logger(__name__)

_TRANSIENT = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
_RETRY_ATTEMPTS = 3
_retry_wait = wait_exponential(multiplier=1, min=1, max=8)  # patchable in tests


def get_chat_model(*, streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """The main chat model — used by the synthesiser and the agents.

    Non-streaming calls go through ``ainvoke()`` (tenacity retry). Streaming
    calls keep langchain's built-in retry (retrying a partly-streamed response
    from ``ainvoke()`` would double-send tokens to the client).
    """
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
        max_retries=2 if streaming else 0,
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
        max_retries=0,
        api_key=settings.OPENAI_API_KEY,
    )


def _log_retry(retry_state) -> None:
    logger.warning(
        "llm_retry",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


async def ainvoke(runnable: Any, messages: Any, **kwargs: Any) -> Any:
    """``runnable.ainvoke`` with 3-attempt exponential-backoff retry on transient
    OpenAI errors (rate limit / timeout / connection / 5xx)."""
    result: Any = None
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(_RETRY_ATTEMPTS),
        wait=_retry_wait,
        retry=retry_if_exception_type(_TRANSIENT),
        before_sleep=_log_retry,
        reraise=True,
    ):
        with attempt:
            result = await runnable.ainvoke(messages, **kwargs)
        if not attempt.retry_state.outcome.failed:  # type: ignore[union-attr]
            attempt.retry_state.set_result(result)
    return result


def tokens_of(response: Any) -> int:
    """Total tokens from an LLM response (AIMessage, or ``include_raw`` dict)."""
    msg = response.get("raw") if isinstance(response, dict) else response
    return (getattr(msg, "usage_metadata", None) or {}).get("total_tokens", 0)


def bump_tokens(usage: dict | None, tokens: int, node: str) -> dict:
    """Accumulate ``token_usage`` for the supervisor's budget guard (CLAUDE.md §4.6)."""
    total = (usage or {}).get("total", 0) + tokens
    by_agent = dict((usage or {}).get("by_agent", {}))
    by_agent[node] = by_agent.get(node, 0) + tokens
    return {"total": total, "by_agent": by_agent}
