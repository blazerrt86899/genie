"""Shared LLM factories + a retrying ``ainvoke`` (CLAUDE.md §3, §4).

**Chat model** — the supervisor's plan, the final streamed answer, and the
``web_search`` / ``task_creator`` agents. Chosen per conversation from
``MODEL_CATALOG`` (the picker in the composer); ``resolve_model_spec(None)`` falls
back to ``settings.LLM_PROVIDER`` + ``settings.chat_model_name``. One unified
``_build()`` covers OpenAI, Groq and Anthropic.

**Utility model** — the cheap internal calls (``prompt_enhancer`` / ``greeting`` /
title / ``validator``). Always ``settings.LLM_PROVIDER`` + ``settings.utility_model_name``;
never user-selectable.

Embeddings always stay on OpenAI. Every non-streaming LLM call goes through
``ainvoke()`` → 4-attempt exponential backoff on transient errors. ``tokens_of()``
pulls the token count off a response so nodes can accumulate
``GenieState['token_usage']`` (the budget guard).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = structlog.get_logger(__name__)

Provider = Literal["openai", "anthropic", "groq"]


# ─── Model catalog (the picker) ──────────────────────────────────────────────


@dataclass(frozen=True)
class ModelSpec:
    """One selectable chat model.

    ``id`` is the stable key the UI/API and ``conversations.model`` store;
    ``model`` is the provider's real model string.
    """

    id: str
    label: str
    provider: Provider
    model: str
    hint: str
    # True → this model's user-facing (streaming) call requests a visible
    # reasoning trace — relayed as `thinking` SSE frames (CLAUDE.md §11).
    thinking: bool = False


MODEL_CATALOG: tuple[ModelSpec, ...] = tuple(
    ModelSpec(*row)
    for row in (
        ("gpt-4o", "GPT-4o", "openai", "gpt-4o-2024-08-06", "Balanced", False),
        ("gpt-4o-mini", "GPT-4o mini", "openai", "gpt-4o-mini", "Fast & cheap", False),
        ("claude-opus", "Claude Opus 5", "anthropic", "claude-opus-5", "Most capable", True),
        ("claude-sonnet", "Claude Sonnet 5", "anthropic", "claude-sonnet-5", "Balanced", True),
        ("claude-haiku", "Claude Haiku 4.5", "anthropic", "claude-haiku-4-5", "Fast", False),
        ("groq-oss-120b", "GPT-OSS 120B", "groq", "openai/gpt-oss-120b", "Very fast", True),
        ("groq-oss-20b", "GPT-OSS 20B", "groq", "openai/gpt-oss-20b", "Fastest", True),
        ("groq-qwen3-27b", "Qwen3 27B", "groq", "qwen/qwen3.8-27b", "Fast", True),
    )
)

_PROVIDER_KEY: dict[Provider, Any] = {
    "openai": lambda: settings.OPENAI_API_KEY,
    "anthropic": lambda: settings.ANTHROPIC_API_KEY,
    "groq": lambda: settings.GROQ_API_KEY,
}


def _provider_ready(provider: Provider) -> bool:
    return bool(_PROVIDER_KEY[provider]())


def available_models() -> list[ModelSpec]:
    """Catalog entries whose provider has an API key configured."""
    return [m for m in MODEL_CATALOG if _provider_ready(m.provider)]


def _default_spec() -> ModelSpec:
    """The model used when nobody picked one — the pre-picker behaviour."""
    provider: Provider = settings.LLM_PROVIDER  # type: ignore[assignment]
    return ModelSpec("_default", "Default", provider, settings.chat_model_name, "")


def default_model_id() -> str | None:
    """Catalog id of the server default, if it maps to one (for the UI)."""
    d = _default_spec()
    match = next(
        (m.id for m in MODEL_CATALOG if m.model == d.model and m.provider == d.provider),
        None,
    )
    if match:
        return match
    avail = available_models()
    return avail[0].id if avail else None


def resolve_model_spec(model_id: str | None) -> ModelSpec:
    """A catalog ``ModelSpec`` for ``model_id``; the server default on miss.

    A miss (unknown id, or a model whose provider lost its key) is logged and
    degrades to the default rather than erroring — ``conversations.model`` can go
    stale.
    """
    if model_id:
        for m in MODEL_CATALOG:
            if m.id == model_id and _provider_ready(m.provider):
                return m
        logger.warning("model_id_unresolved", model_id=model_id)
    return _default_spec()


def _transient_errors() -> tuple[type[Exception], ...]:
    """Retryable errors from every LLM SDK that might be in play."""
    errs: list[type[Exception]] = []
    for mod in ("openai", "groq", "anthropic"):
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
    provider: Provider,
    model: str,
    *,
    streaming: bool,
    temperature: float,
    max_tokens: int | None,
    light: bool = False,
    thinking: bool = False,
) -> BaseChatModel:
    max_retries = 2 if streaming else 0  # streaming keeps langchain's own retry

    if provider == "groq":
        from langchain_groq import ChatGroq

        kwargs: dict[str, Any] = {}
        if light:
            effort = _groq_light_reasoning(model)
            if effort:
                kwargs["reasoning_effort"] = effort
        # gpt-oss/qwen3 already emit a visible reasoning trace by default
        # (additional_kwargs["reasoning_content"] on each streamed chunk) unless
        # quieted by `light` above — nothing extra to request here.
        # Groq streams a final usage chunk automatically → usage_metadata is set.
        return ChatGroq(
            model=model,
            temperature=temperature,
            streaming=streaming,
            max_tokens=max_tokens,
            max_retries=max_retries,
            api_key=settings.GROQ_API_KEY,
            **kwargs,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        headers: dict[str, str] = {}
        if settings.ANTHROPIC_WORKSPACE_ID:  # identity-linked keys need this
            headers["anthropic-workspace-id"] = settings.ANTHROPIC_WORKSPACE_ID
        anthropic_kwargs: dict[str, Any] = {}
        # Only the synthesiser's streamed, user-facing call requests a visible
        # reasoning trace (relayed as `thinking` SSE frames — CLAUDE.md §11).
        # No `budget_tokens` — rejected (400) on the Claude 5 tier.
        if thinking and streaming:
            anthropic_kwargs["thinking"] = {"type": "adaptive"}
        # NB: no ``temperature`` — claude-opus-5 / claude-sonnet-5 reject it (400).
        # Anthropic requires a max_tokens; give streamed answers real room.
        return ChatAnthropic(
            model=model,
            streaming=streaming,
            max_tokens=max_tokens or 8192,
            max_retries=max_retries,
            api_key=settings.ANTHROPIC_API_KEY,
            default_headers=headers or None,
            **anthropic_kwargs,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        streaming=streaming,
        stream_usage=streaming,  # include token usage on the final streamed chunk
        max_tokens=max_tokens,
        max_retries=max_retries,
        api_key=settings.OPENAI_API_KEY,
    )


def get_chat_model(
    *, model_id: str | None = None, streaming: bool = True, temperature: float = 0.7
) -> BaseChatModel:
    """The main chat model — the synthesiser and the agents.

    ``model_id`` is a ``MODEL_CATALOG`` id (from ``conversations.model`` /
    ``GenieState['model']``); ``None`` → the server default. Non-streaming calls
    go through ``ainvoke()`` (tenacity retry); streaming calls keep langchain's
    own retry (retrying a partly-streamed response would double-send tokens).
    """
    spec = resolve_model_spec(model_id)
    logger.debug(
        "llm_model_build",
        model_id=model_id,
        provider=spec.provider,
        model=spec.model,
        streaming=streaming,
        temperature=temperature,
        thinking=spec.thinking,
    )
    return _build(
        spec.provider,
        spec.model,
        streaming=streaming,
        temperature=temperature,
        max_tokens=None,
        thinking=spec.thinking,
    )


def provider_for(model_id: str | None) -> Provider:
    """The provider that will actually serve ``model_id`` (after fallback)."""
    return resolve_model_spec(model_id).provider


def system_message(text: str, *, model_id: str | None = None, cache: bool = True):
    """A ``SystemMessage`` for a large, static prompt.

    On Anthropic, marks the block with a ``cache_control`` breakpoint so repeated
    turns pay ~10% for the cached prefix (5-min TTL). OpenAI caches long prefixes
    automatically; Groq has no prompt cache — both get a plain string.
    """
    if cache and provider_for(model_id) == "anthropic":
        return SystemMessage(
            content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        )
    return SystemMessage(content=text)


def get_utility_model(*, temperature: float = 0.4, max_tokens: int | None = None) -> BaseChatModel:
    """A cheap model for small, non-streamed jobs (routing, greetings, titles).

    On Groq the utility model (gpt-oss / qwen3) is a reasoning model — ``light=True``
    trims the reasoning pass to its minimum, but callers passing a tight
    ``max_tokens`` must still leave a little headroom for it (see ``_build``).
    """
    provider: Provider = settings.LLM_PROVIDER  # type: ignore[assignment]
    model = settings.utility_model_name
    logger.debug(
        "llm_utility_model_build",
        provider=provider,
        model=model,
        max_tokens=max_tokens,
    )
    return _build(
        provider,
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
