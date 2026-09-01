"""Shared LLM factories + a retrying ``ainvoke`` (CLAUDE.md §3, §4).

The chat backend is picked by ``settings.LLM_PROVIDER`` — ``openai`` (default) or
``groq`` (OpenAI-credit-free, for testing). Both SDKs raise the same exception
names, so the retry / token helpers don't care which is active. Embeddings always
stay on OpenAI.

Every non-streaming LLM call goes through ``ainvoke()`` → 4-attempt exponential
backoff on transient errors. ``tokens_of()`` pulls the token count off a response
so nodes can accumulate ``GenieState['token_usage']`` (the budget guard).
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = structlog.get_logger(__name__)


def _transient_errors() -> tuple[type[Exception], ...]:
    """Retryable errors from whichever LLM SDK is in play."""
    errs: list[type[Exception]] = []
    for mod in ("openai", "groq"):
        try:
            m = __import__(mod)
            errs += [
                m.RateLimitError,
                m.APITimeoutError,
                m.APIConnectionError,
                m.InternalServerError,
            ]
        except (ImportError, AttributeError):
            continue
    return tuple(errs)


_TRANSIENT = _transient_errors()
# Groq's free tier is 8k TPM — a 429 asks for a ~10-15s wait, so give the backoff
# enough headroom to actually ride one out rather than give up after ~3s.
_RETRY_ATTEMPTS = 4
_retry_wait = wait_exponential(multiplier=2, min=2, max=30)  # patchable in tests


def _groq_light_reasoning(model: str) -> str | None:
    """The smallest valid ``reasoning_effort`` for a Groq reasoning model.

    gpt-oss-* and qwen3* burn completion tokens on a hidden reasoning pass before
    emitting content, so a tight ``max_tokens`` returns an EMPTY answer
    (finish_reason="length"). For utility calls we want that pass as short as
    possible (also cheaper against the free-tier TPM cap). gpt-oss rejects
    "none" — "low" is its floor; qwen3 accepts "none".
    """
    if model.startswith("openai/gpt-oss"):
        return "low"
    if model.startswith("qwen/qwen3"):
        return "none"
    return None


def _build(
    model: str,
    *,
    streaming: bool,
    temperature: float,
    max_tokens: int | None,
    light: bool = False,
) -> BaseChatModel:
    max_retries = 2 if streaming else 0  # streaming keeps langchain's own retry
    if settings.LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq

        kwargs: dict[str, Any] = {}
        if light:
            effort = _groq_light_reasoning(model)
            if effort:
                kwargs["reasoning_effort"] = effort

        return ChatGroq(
            model=model,
            temperature=temperature,
            streaming=streaming,
            max_tokens=max_tokens,
            max_retries=max_retries,
            api_key=settings.GROQ_API_KEY,
            **kwargs,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        streaming=streaming,
        max_tokens=max_tokens,
        max_retries=max_retries,
        api_key=settings.OPENAI_API_KEY,
    )


def get_chat_model(*, streaming: bool = True, temperature: float = 0.7) -> BaseChatModel:
    """The main chat model — used by the synthesiser and the agents.

    Non-streaming calls go through ``ainvoke()`` (tenacity retry). Streaming
    calls keep langchain's built-in retry (retrying a partly-streamed response
    would double-send tokens to the client).
    """
    model = settings.chat_model_name
    logger.debug(
        "llm_model_build",
        provider=settings.LLM_PROVIDER,
        model=model,
        streaming=streaming,
        temperature=temperature,
    )
    return _build(model, streaming=streaming, temperature=temperature, max_tokens=None)


def get_utility_model(*, temperature: float = 0.4, max_tokens: int | None = None) -> BaseChatModel:
    """A cheap model for small, non-streamed jobs (routing, greetings, titles).

    On Groq the utility model (gpt-oss / qwen3) is a reasoning model — ``light=True``
    trims the reasoning pass to its minimum, but callers passing a tight
    ``max_tokens`` must still leave a little headroom for it (see ``_build``).
    """
    model = settings.utility_model_name
    logger.debug(
        "llm_utility_model_build",
        provider=settings.LLM_PROVIDER,
        model=model,
        max_tokens=max_tokens,
    )
    return _build(
        model,
        streaming=False,
        temperature=temperature,
        max_tokens=max_tokens,
        light=True,
    )


def _log_retry(retry_state) -> None:
    logger.warning(
        "llm_retry",
        attempt=retry_state.attempt_number,
        error=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


async def ainvoke(runnable: Any, messages: Any, **kwargs: Any) -> Any:
    """``runnable.ainvoke`` with 4-attempt exponential-backoff retry on transient
    provider errors (rate limit / timeout / connection / 5xx)."""
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
