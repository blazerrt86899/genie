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
from langchain_core.messages import AIMessage, HumanMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor.graph import get_runtime_graph
from app.config import settings
from app.core.logging import preview
from app.core.streaming import format_sse_event, sse_done, sse_error
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.document_repo import DocumentRepository
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

    # ── Input guardrail — redact live secrets / card / SSN BEFORE the message is
    # persisted or sent to any LLM; keep ordinary PII (the user's own contact
    # details are often the point). See core/guardrails.py.
    guardrail_note: dict | None = None
    if settings.GUARDRAILS_ENABLED and settings.GUARDRAIL_INPUT_ENABLED:
        from app.core import guardrails

        findings = guardrails.scan(message)
        to_redact = [f for f in findings if f.severity == "secret"
                     or f.kind in ("ssn", "credit_card")]
        flagged = sorted({f.kind for f in findings
                          if f.severity == "pii" and f.kind not in ("ssn", "credit_card")})
        if to_redact:
            message = guardrails.redact(message, to_redact)
        if findings:
            redacted_kinds = sorted({f.kind for f in to_redact})
            note_bits = []
            if redacted_kinds:
                note_bits.append(
                    f"Hid {guardrails.summarize([f for f in findings if f.kind in redacted_kinds])}"
                    " before sending — never share live secrets or card numbers."
                )
            if flagged:
                note_bits.append(
                    f"Heads-up: your message contains "
                    f"{guardrails.summarize([f for f in findings if f.kind in flagged])}."
                )
            guardrail_note = {
                "redacted": redacted_kinds,
                "flagged": flagged,
                "message": " ".join(note_bits),
            }
            logger.info(
                "guardrail_input", redacted=redacted_kinds, flagged=flagged,
                findings=len(findings),
            )

    msg_meta: dict = {}
    if guardrail_note:
        msg_meta["guardrail"] = guardrail_note
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
    run_payload: dict = {
        "conversation_id": str(conversation.id),
        "message": message,
        "client_hour": client_hour,
        "attachment_ids": linked_ids,
    }
    if guardrail_note:
        run_payload["guardrail"] = guardrail_note
    await redis.setex(_run_key(run_id), _RUN_TTL_SECONDS, json.dumps(run_payload))
    logger.info(
        "chat_turn_accepted",
        run_id=run_id,
        conversation_id=str(conversation.id),
        run_ttl_s=_RUN_TTL_SECONDS,
    )
    return run_id, str(conversation.id)


async def regenerate_turn(
    db: AsyncSession,
    redis: Redis,
    user: User,
    conversation_id: str,
    from_message_id: str,
    edit: str | None = None,
) -> tuple[str, str]:
    """Truncate the conversation at ``from_message_id`` and re-run from there.

    - target is an **assistant** message → regenerate it (drop it + everything
      after; keep the user message before it).
    - target is a **user** message → retry it (drop everything after); if ``edit``
      is given, replace its text first.

    Resets the LangGraph thread; ``_generate`` replays the surviving history.
    """
    try:
        cid = uuid.UUID(conversation_id)
        target_id = uuid.UUID(from_message_id)
    except ValueError as exc:
        raise ValueError("not found") from exc

    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_for_user(cid, user.id)
    if conversation is None:
        raise ValueError("conversation not found")

    msg_repo = MessageRepository(db)
    rows = await msg_repo.list_for_conversation(cid)
    idx = next((i for i, m in enumerate(rows) if m.id == target_id), None)
    if idx is None:
        raise ValueError("message not found")
    target = rows[idx]

    if target.role == "assistant":
        anchor = next(
            (rows[j] for j in range(idx - 1, -1, -1) if rows[j].role == "user"), None
        )
        if anchor is None:
            raise ValueError("nothing to regenerate — no preceding user message")
    else:
        anchor = target
        if edit is not None:
            new_text = edit.strip()
            if not new_text:
                raise ValueError("edited message must not be empty")
            if settings.GUARDRAILS_ENABLED and settings.GUARDRAIL_INPUT_ENABLED:
                from app.core import guardrails

                secrets = [f for f in guardrails.scan(new_text)
                           if f.severity == "secret" or f.kind in ("ssn", "credit_card")]
                if secrets:
                    new_text = guardrails.redact(new_text, secrets)
                    logger.info("guardrail_input", stage="edit",
                                redacted=sorted({f.kind for f in secrets}))
            await msg_repo.set_content(anchor.id, user.id, new_text)
            anchor.content = new_text

    deleted = await msg_repo.delete_after(cid, anchor.created_at, inclusive=False)

    try:
        await get_runtime_graph().checkpointer.adelete_thread(conversation_id)
    except Exception:  # noqa: BLE001 — orphan checkpoint rows are harmless
        logger.warning("checkpointer_thread_delete_failed", conversation_id=conversation_id)

    await conv_repo.touch(cid)

    run_id = str(uuid.uuid4())
    await redis.setex(
        _run_key(run_id),
        _RUN_TTL_SECONDS,
        json.dumps(
            {
                "conversation_id": conversation_id,
                "mode": "regenerate",
                "message": anchor.content,
                "client_hour": None,
                "attachment_ids": [],
            }
        ),
    )
    logger.info(
        "chat_regenerate_accepted",
        run_id=run_id,
        conversation_id=conversation_id,
        target_role=target.role,
        edited=bool(edit),
        deleted=deleted,
    )
    return run_id, conversation_id


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
    mode: str | None = payload.get("mode")  # None (normal turn) | "regenerate"
    guardrail_note: dict | None = payload.get("guardrail")

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
    rag_settings: dict | None = None
    has_kb = False
    if conversation.project_id is not None:
        project = await ProjectRepository(db).get_for_user(conversation.project_id, user.id)
        if project is not None:
            project_instructions = project.instructions
            rag_settings = project.rag_settings or {}
            has_kb = (
                await DocumentRepository(db).count_ready_for_project(conversation.project_id)
            ) > 0
            logger.info(
                "chat_project_context_loaded",
                project_id=str(conversation.project_id),
                instruction_chars=len(project_instructions or ""),
                has_kb=has_kb,
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

    # A regenerate/retry/edit reset the checkpointer thread — replay the surviving
    # history (from the messages table, the display source of truth) as the seed.
    if mode == "regenerate":
        rows = await MessageRepository(db).list_for_conversation(conversation.id)
        seed_messages = [
            HumanMessage(content=r.content)
            if r.role == "user"
            else AIMessage(content=r.content)
            for r in rows
        ]
        if not seed_messages:
            seed_messages = [HumanMessage(content=message)]
        logger.info("chat_regenerate_seed", run_id=run_id, history_messages=len(seed_messages))
    else:
        seed_messages = [HumanMessage(content=message)]

    graph = get_runtime_graph()
    config = {"configurable": {"thread_id": conversation_id}}
    state = {
        "messages": seed_messages,
        "user_id": str(user.id),
        "conversation_id": conversation_id,
        "project_instructions": project_instructions,
        "client_hour": client_hour,
        "model": conversation.model,
        "attachments": attachments,
        "rag_settings": rag_settings,
        "has_kb": has_kb,
        "needs_documents": False,
        "retrieved_chunks": [],
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
        "metadata": {
            "project_id": str(conversation.project_id) if conversation.project_id else None
        },
    }

    if guardrail_note:
        yield format_sse_event(
            "guardrail",
            types=list(guardrail_note.get("redacted", []))
            + list(guardrail_note.get("flagged", [])),
            redacted=bool(guardrail_note.get("redacted")),
            message=guardrail_note.get("message", ""),
        ), None

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
            elif name == "guardrail":
                logger.info(
                    "chat_guardrail",
                    run_id=run_id,
                    types=data.get("types"),
                    redacted=data.get("redacted"),
                )
                yield format_sse_event(
                    "guardrail",
                    types=list(data.get("types") or []),
                    redacted=bool(data.get("redacted")),
                    message=data.get("message") or "",
                ), None
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
    graph_snapshot = None
    cached_hit: dict | None = None
    if not pairs:
        # Nothing streamed — recover the reply from the graph state (this is also
        # the response-cache-hit path: cache_lookup wrote the AIMessage + skipped
        # the synthesiser).
        logger.warning("chat_no_streamed_output", run_id=run_id)
        try:
            graph_snapshot = await graph.aget_state(config)
            values = graph_snapshot.values if graph_snapshot else {}
            msgs = values.get("messages", [])
            text = str(msgs[-1].content).strip() if msgs else ""
            cached_hit = (values.get("metadata") or {}).get("cache_hit")
            if text and cached_hit:
                yield format_sse_event("message_agents", agents=["cache"]), None
                for i in range(0, len(text), 24):  # a light typing feel
                    yield format_sse_event("token", content=text[i : i + 24]), None
                pairs = [(text, ["cache"])]
            elif text:
                pairs = [(text, [])]
                yield format_sse_event("token", content=text), None
        except Exception:  # noqa: BLE001
            logger.warning("chat_state_fetch_failed", run_id=run_id)

    # Structured sources (web_search etc.) — surfaced as link cards, not baked
    # into the answer text.
    sources: list[dict] = []
    snap_values: dict = {}
    try:
        snap = graph_snapshot or await graph.aget_state(config)
        snap_values = dict(snap.values) if snap else {}
        seen: set[str] = set()
        for r in (snap_values.get("intermediate_results") or {}).values():
            for s in r.get("sources") or []:
                url = (s.get("url") or "").strip()
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"title": s.get("title") or url, "url": url})
    except Exception:  # noqa: BLE001
        logger.warning("chat_sources_fetch_failed", run_id=run_id)
    if sources:
        yield format_sse_event("sources", items=sources), None

    # The graph nodes accumulate `token_usage.total` via `models.bump_tokens`
    # (prompt_enhancer + supervisor + synthesiser + validator) — that's the
    # authoritative count; the streamed-event sum is a fallback.
    graph_tokens = int((snap_values.get("token_usage") or {}).get("total", 0) or 0)
    total_tokens = max(total_tokens, graph_tokens)

    logger.info(
        "chat_graph_done",
        run_id=run_id,
        messages=len(pairs),
        message_agents=[a for _, a in pairs],
        streamed_token_frames=token_frames,
        total_tokens=total_tokens,
        graph_tokens=graph_tokens,
        sources=len(sources),
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
            if "cache" in agents:
                meta["cached"] = True
            if sources and i == last:
                meta["sources"] = sources
            if langsmith_run_id and i == last:
                meta["langsmith_run_id"] = langsmith_run_id
            if total_tokens and i == last:
                meta["total_tokens"] = total_tokens
            await MessageRepository(db).add_message(
                conversation.id,
                user.id,
                "assistant",
                part,
                metadata=meta,
                created_at=now + timedelta(milliseconds=10 * i),
            )
        await conv_repo.touch(conversation.id)

        # Cache a pure-knowledge answer for the next near-identical question:
        # one message, no agents, no sources, no KB, first turn of the chat,
        # a non-time-sensitive query — and not itself a cache/regenerate reply.
        enhanced_q = snap_values.get("enhanced_query") or message
        if (
            mode != "regenerate"
            and not cached_hit
            and len(pairs) == 1
            and not snap_values.get("plan")
            and not sources
            and not snap_values.get("retrieved_chunks")
            and len(seed_messages) == 1
        ):
            from app.services import cache_service

            try:
                await cache_service.store(
                    db, str(user.id), enhanced_q, answer, conversation.model
                )
            except Exception:  # noqa: BLE001 — caching is best-effort
                logger.warning("cache_store_failed", run_id=run_id, exc_info=True)

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
