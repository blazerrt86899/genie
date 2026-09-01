"""Chat orchestration (CLAUDE.md §11).

Two-step flow — ``create_turn`` persists the user message and stashes the pending
run in Redis; ``stream_turn`` runs the supervisor graph and streams SSE frames,
then persists the assistant reply. One turn can produce **several** assistant
messages (e.g. a greeting, then the answer) — split on ``message_break`` frames.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import structlog
from langchain_core.messages import HumanMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor.graph import get_runtime_graph
from app.config import settings
from app.core.logging import preview
from app.core.streaming import format_sse_event, sse_done, sse_error
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.repositories.project_repo import ProjectRepository
from app.services import attachment_service
from app.services.title_service import generate_title

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
    project_id: str | None = None,
    client_hour: int | None = None,
    model: str | None = None,
    attachment_ids: list[str] | None = None,
) -> tuple[str, str]:
    """Persist the user message, return ``(run_id, conversation_id)``."""
    attachment_ids = attachment_ids or []
    logger.info(
        "chat_create_turn_start",
        user_id=str(user.id),
        conversation_id=conversation_id,
        project_id=project_id,
        client_hour=client_hour,
        model=model,
        attachments=len(attachment_ids),
        message_chars=len(message),
        message_preview=preview(message),
    )
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)

    if conversation_id:
        conversation = await conv_repo.get_for_user(uuid.UUID(conversation_id), user.id)
        if conversation is None:
            logger.warning(
                "chat_conversation_not_found",
                conversation_id=conversation_id,
                user_id=str(user.id),
            )
            raise ValueError("conversation not found")
        logger.debug("chat_using_existing_conversation", conversation_id=conversation_id)
        if model and model != conversation.model:
            # Switching model mid-conversation sticks for the next turn onward.
            await conv_repo.set_model(conversation.id, user.id, model)
    else:
        pid: uuid.UUID | None = None
        if project_id:
            project = await ProjectRepository(db).get_for_user(
                uuid.UUID(project_id), user.id
            )
            if project is None:
                logger.warning(
                    "chat_project_not_found", project_id=project_id, user_id=str(user.id)
                )
                raise ValueError("project not found")
            pid = project.id
        conversation = await conv_repo.create(
            user.id, title=None, project_id=pid, model=model
        )

    msg_meta: dict = {}
    linked_ids: list[str] = []
    if attachment_ids:
        atts = await attachment_service.list_for_ids(db, user.id, attachment_ids)
        linked_ids = [str(a.id) for a in atts]
        msg_meta["attachments"] = [
            {"id": str(a.id), "filename": a.filename, "kind": a.kind, "char_count": a.char_count}
            for a in atts
        ]

    user_msg = await msg_repo.add_message(
        conversation.id, user.id, "user", message, metadata=msg_meta or None
    )
    if linked_ids:
        await attachment_service.link(db, user.id, linked_ids, conversation.id, user_msg.id)
        logger.info(
            "chat_turn_attachments",
            conversation_id=str(conversation.id),
            attachments=len(linked_ids),
        )
    await conv_repo.touch(conversation.id)

    run_id = str(uuid.uuid4())
    await redis.setex(
        _run_key(run_id),
        _RUN_TTL_SECONDS,
        json.dumps(
            {
                "conversation_id": str(conversation.id),
                "message": message,
                "client_hour": client_hour,
                "attachment_ids": linked_ids,
            }
        ),
    )
    logger.info(
        "chat_turn_accepted",
        run_id=run_id,
        conversation_id=str(conversation.id),
        run_ttl_s=_RUN_TTL_SECONDS,
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
    logger.info("chat_stream_start", run_id=run_id, conversation_id=conversation_id)
    raw = await redis.get(_run_key(run_id))
    if raw is None:
        logger.warning("chat_run_not_found", run_id=run_id)
        yield sse_error("unknown or expired run", "run_not_found"), None
        return
    payload = json.loads(raw)
    message: str = payload["message"]
    client_hour = payload.get("client_hour")
    attachment_ids: list[str] = payload.get("attachment_ids") or []

    if payload["conversation_id"] != conversation_id:
        logger.warning(
            "chat_run_conversation_mismatch",
            run_id=run_id,
            run_conversation_id=payload["conversation_id"],
            requested=conversation_id,
        )
        yield sse_error("run does not belong to this conversation", "run_mismatch"), None
        return

    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_for_user(uuid.UUID(conversation_id), user.id)
    if conversation is None:
        logger.warning("chat_conversation_gone", conversation_id=conversation_id)
        yield sse_error("conversation not found", "not_found"), None
        return

    if not settings.llm_configured:
        logger.error("chat_llm_not_configured", provider=settings.LLM_PROVIDER)
        yield sse_error(
            f"no API key for LLM_PROVIDER={settings.LLM_PROVIDER}", "llm_not_configured"
        ), None
        return

    project_instructions: str | None = None
    if conversation.project_id is not None:
        project = await ProjectRepository(db).get_for_user(conversation.project_id, user.id)
        if project is not None:
            project_instructions = project.instructions
            logger.info(
                "chat_project_instructions_loaded",
                project_id=str(conversation.project_id),
                instruction_chars=len(project_instructions or ""),
            )

    attachments: list[dict] = []
    if attachment_ids:
        atts = await attachment_service.list_for_ids(db, user.id, attachment_ids)
        attachments = [
            {"filename": a.filename, "kind": a.kind, "text": a.content} for a in atts
        ]
        logger.info(
            "chat_attachments_loaded",
            run_id=run_id,
            count=len(attachments),
            total_chars=sum(a.char_count for a in atts),
        )

    graph = get_runtime_graph()
    config = {"configurable": {"thread_id": conversation_id}}
    state = {
        "messages": [HumanMessage(content=message)],
        "user_id": str(user.id),
        "conversation_id": conversation_id,
        "project_instructions": project_instructions,
        "client_hour": client_hour,
        "model": conversation.model,
        "attachments": attachments,
        "intent": None,
        "enhanced_query": None,
        "plan": [],
        "supervisor_turns": 0,
        "active_agents": [],
        "intermediate_results": {},
        "streamed_segments": [],
        "final_response": None,
        "validation": None,
        "token_usage": {"total": 0, "by_agent": {}},
        "user_memories": [],
        "should_interrupt": False,
        "metadata": {},
    }

    logger.info(
        "chat_graph_invoke",
        run_id=run_id,
        thread_id=conversation_id,
        has_project_instructions=project_instructions is not None,
        client_hour=client_hour,
        model=conversation.model,
    )

    total_tokens = 0
    token_frames = 0
    langsmith_run_id: str | None = None
    parts: list[str] = [""]  # one entry per assistant message this turn
    part_agents: list[list[str]] = [[]]  # agents that produced each part
    async for event in graph.astream_events(state, config=config, version="v2"):
        # The first event with no parent is the root graph run — its id is the
        # LangSmith trace id (when tracing is enabled).
        if langsmith_run_id is None and not event.get("parent_ids"):
            langsmith_run_id = event.get("run_id")

        kind = event["event"]
        if kind == "on_chat_model_stream":
            # Only the synthesiser's tokens are the user-facing answer — the
            # supervisor and the agents also call models, silently.
            if (event.get("metadata") or {}).get("langgraph_node") != "synthesiser":
                continue
            chunk = event["data"]["chunk"].content
            if chunk:
                parts[-1] += chunk
                token_frames += 1
                yield format_sse_event("token", content=chunk), None
        elif kind == "on_chat_model_end":
            usage = getattr(event["data"].get("output"), "usage_metadata", None)
            if usage:
                node = (event.get("metadata") or {}).get("langgraph_node")
                total_tokens += usage.get("total_tokens", 0)
                logger.debug(
                    "chat_model_call_done",
                    node=node,
                    call_tokens=usage.get("total_tokens", 0),
                    run_total_tokens=total_tokens,
                )
        elif kind == "on_custom_event":
            name = event.get("name")
            data = event.get("data") or {}
            if name == "agent_start":
                logger.info(
                    "chat_agent_start",
                    run_id=run_id,
                    agent=data.get("agent"),
                    task=preview(data.get("task", ""), 100),
                )
                yield format_sse_event(
                    "agent_start", agent=data.get("agent"), run_id=run_id
                ), None
            elif name == "agent_end":
                logger.info(
                    "chat_agent_end",
                    run_id=run_id,
                    agent=data.get("agent"),
                    status=data.get("status"),
                )
                yield format_sse_event(
                    "agent_end", agent=data.get("agent"), status=data.get("status")
                ), None
            elif name == "plan":
                steps = data.get("steps", [])
                logger.info(
                    "chat_plan",
                    run_id=run_id,
                    steps=[
                        {"agent": s.get("agent"), "status": s.get("status")} for s in steps
                    ],
                )
                yield format_sse_event("plan", steps=steps), None
            elif name in ("task_created", "task_updated"):
                task_dict = data.get("task") or {}
                logger.info(
                    f"chat_{name}",
                    run_id=run_id,
                    task_id=task_dict.get("id"),
                    status=task_dict.get("status"),
                )
                yield format_sse_event(name, task=task_dict), None
            elif name == "tasks_archived":
                logger.info("chat_tasks_archived", run_id=run_id, count=data.get("count"))
                yield format_sse_event("tasks_archived", count=data.get("count", 0)), None
            elif name == "message_break":
                # start a new assistant message
                parts.append("")
                part_agents.append([])
                logger.debug("chat_message_break", run_id=run_id, message_index=len(parts) - 1)
                yield format_sse_event("message_break"), None
            elif name == "message_agents":
                agents = list(data.get("agents") or [])
                part_agents[-1] = agents
                yield format_sse_event("message_agents", agents=agents), None
            elif name == "segment":
                # an already-user-ready agent output (e.g. the greeting)
                seg = str(data.get("text") or "").strip()
                if seg:
                    parts[-1] += seg
                    logger.debug(
                        "chat_segment", run_id=run_id, agent=data.get("agent"), chars=len(seg)
                    )
                    yield format_sse_event("token", content=seg), None

    pairs = [(p.strip(), a) for p, a in zip(parts, part_agents, strict=False) if p.strip()]
    if not pairs:
        # Nothing streamed — recover the reply from the graph state.
        logger.warning("chat_no_streamed_output", run_id=run_id)
        try:
            snapshot = await graph.aget_state(config)
            msgs = snapshot.values.get("messages", []) if snapshot else []
            text = str(msgs[-1].content).strip() if msgs else ""
            if text:
                pairs = [(text, [])]
                yield format_sse_event("token", content=text), None
        except Exception:  # noqa: BLE001
            logger.warning("chat_state_fetch_failed", run_id=run_id)

    logger.info(
        "chat_graph_done",
        run_id=run_id,
        messages=len(pairs),
        message_agents=[a for _, a in pairs],
        streamed_token_frames=token_frames,
        total_tokens=total_tokens,
    )
    answer = "\n\n".join(p for p, _ in pairs)
    title: str | None = None
    if pairs:
        now = datetime.now(UTC)
        last = len(pairs) - 1
        for i, (part, agents) in enumerate(pairs):
            meta: dict = {}
            if agents:
                meta["agents"] = agents
            if langsmith_run_id and i == last:
                meta["langsmith_run_id"] = langsmith_run_id
            await MessageRepository(db).add_message(
                conversation.id,
                user.id,
                "assistant",
                part,
                metadata=meta,
                created_at=now + timedelta(milliseconds=10 * i),
            )
        await conv_repo.touch(conversation.id)

        # First real exchange in this chat → auto-title it (Claude-style heading).
        if conversation.title is None:
            logger.debug("chat_title_generating", conversation_id=conversation_id)
            title = await generate_title(message, answer)
            if title:
                await conv_repo.set_title(conversation.id, user.id, title)
                yield (
                    format_sse_event(
                        "title", conversation_id=conversation_id, title=title
                    ),
                    None,
                )

    await redis.delete(_run_key(run_id))
    logger.info(
        "chat_turn_completed",
        run_id=run_id,
        conversation_id=conversation_id,
        langsmith_run_id=langsmith_run_id,
        total_tokens=total_tokens,
        assistant_messages=len(pairs),
        answer_chars=len(answer),
        titled=bool(title),
    )
    yield "", {
        "total_tokens": total_tokens,
        "langsmith_run_id": langsmith_run_id,
        "title": title,
    }


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
        logger.exception("chat_stream_failed", run_id=run_id, conversation_id=conversation_id)
        yield sse_error(str(exc), "chat_error")

    yield sse_done(
        total_tokens=done_info.get("total_tokens", 0),
        run_id=run_id,
        langsmith_run_id=done_info.get("langsmith_run_id"),
        title=done_info.get("title"),
    )


async def delete_conversation(db: AsyncSession, user: User, conversation_id: str) -> bool:
    """Delete a conversation (+ its messages via cascade) and its LangGraph thread."""
    logger.info(
        "chat_delete_conversation_start",
        conversation_id=conversation_id,
        user_id=str(user.id),
    )
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        logger.warning("chat_delete_bad_uuid", conversation_id=conversation_id)
        return False

    ok = await ConversationRepository(db).delete_for_user(cid, user.id)
    if ok:
        try:
            await get_runtime_graph().checkpointer.adelete_thread(conversation_id)
            logger.info("checkpointer_thread_deleted", conversation_id=conversation_id)
        except Exception:  # noqa: BLE001  — best-effort; orphan checkpoint rows are harmless
            logger.warning("checkpointer_thread_delete_failed", conversation_id=conversation_id)
    return ok
