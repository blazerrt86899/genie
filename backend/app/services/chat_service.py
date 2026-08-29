"""Chat orchestration (CLAUDE.md §11).

Interim: a single-node LangGraph ``chat`` graph, no supervisor/agents. Two-step
flow — ``create_turn`` persists the user message and stashes the pending run in
Redis; ``stream_turn`` runs the graph and streams SSE frames, then persists the
assistant message.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import structlog
from langchain_core.messages import HumanMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor.graph import get_runtime_graph
from app.config import settings
from app.core.streaming import format_sse_event, sse_done, sse_error
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.message_repo import MessageRepository

logger = structlog.get_logger(__name__)

_RUN_TTL_SECONDS = 300


def _run_key(run_id: str) -> str:
    return f"run:{run_id}"


async def create_turn(
    db: AsyncSession,
    redis: Redis,
    user: User,
    message: str,
    conversation_id: str | None,
) -> tuple[str, str]:
    """Persist the user message, return ``(run_id, conversation_id)``."""
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    if conversation_id:
        conversation = await conv_repo.get_for_user(uuid.UUID(conversation_id), user.id)
        if conversation is None:
            raise ValueError("conversation not found")
    else:
        conversation = await conv_repo.create(user.id, title=message[:60])

    await msg_repo.add_message(conversation.id, user.id, "user", message)

    run_id = str(uuid.uuid4())
    await redis.setex(
        _run_key(run_id),
        _RUN_TTL_SECONDS,
        json.dumps({"conversation_id": str(conversation.id), "message": message}),
    )
    return run_id, str(conversation.id)


async def _generate(
    db: AsyncSession,
    redis: Redis,
    user: User,
    conversation_id: str,
    run_id: str,
) -> AsyncIterator[tuple[str, dict | None]]:
    """Yield ``(sse_frame, done_info)`` — ``done_info`` is set only on the final
    yield: ``{"total_tokens", "langsmith_run_id"}``."""
    raw = await redis.get(_run_key(run_id))
    if raw is None:
        yield sse_error("unknown or expired run", "run_not_found"), None
        return
    payload = json.loads(raw)
    message: str = payload["message"]

    if payload["conversation_id"] != conversation_id:
        yield sse_error("run does not belong to this conversation", "run_mismatch"), None
        return

    conversation = await ConversationRepository(db).get_for_user(
        uuid.UUID(conversation_id), user.id
    )
    if conversation is None:
        yield sse_error("conversation not found", "not_found"), None
        return

    if not settings.llm_configured:
        yield sse_error("OPENAI_API_KEY is not set", "llm_not_configured"), None
        return

    graph = get_runtime_graph()
    config = {"configurable": {"thread_id": conversation_id}}
    state = {
        "messages": [HumanMessage(content=message)],
        "user_id": str(user.id),
        "conversation_id": conversation_id,
    }

    total_tokens = 0
    langsmith_run_id: str | None = None
    answer_parts: list[str] = []
    async for event in graph.astream_events(state, config=config, version="v2"):
        # The first event with no parent is the root graph run — its id is the
        # LangSmith trace id (when tracing is enabled).
        if langsmith_run_id is None and not event.get("parent_ids"):
            langsmith_run_id = event.get("run_id")

        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            if chunk:
                answer_parts.append(chunk)
                yield format_sse_event("token", content=chunk), None
        elif kind == "on_chat_model_end":
            usage = getattr(event["data"].get("output"), "usage_metadata", None)
            if usage:
                total_tokens = usage.get("total_tokens", 0)

    answer = "".join(answer_parts)
    if answer:
        meta: dict = {}
        if langsmith_run_id:
            meta["langsmith_run_id"] = langsmith_run_id
        await MessageRepository(db).add_message(
            conversation.id, user.id, "assistant", answer, metadata=meta
        )
    await redis.delete(_run_key(run_id))
    logger.info(
        "chat_turn_completed",
        run_id=run_id,
        langsmith_run_id=langsmith_run_id,
        total_tokens=total_tokens,
    )
    yield "", {"total_tokens": total_tokens, "langsmith_run_id": langsmith_run_id}


async def stream_turn(
    db: AsyncSession,
    redis: Redis,
    user: User,
    conversation_id: str,
    run_id: str,
) -> AsyncIterator[str]:
    """Yield SSE frames for one assistant turn. Always ends with a ``done`` event
    (error event first if something failed — CLAUDE.md §16)."""
    done_info: dict = {}
    try:
        async for frame, info in _generate(db, redis, user, conversation_id, run_id):
            if frame:
                yield frame
            if info:
                done_info = info
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat_stream_failed", run_id=run_id)
        yield sse_error(str(exc), "chat_error")

    yield sse_done(
        total_tokens=done_info.get("total_tokens", 0),
        run_id=run_id,
        langsmith_run_id=done_info.get("langsmith_run_id"),
    )
