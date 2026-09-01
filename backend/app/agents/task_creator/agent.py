"""Task Creator agent (CLAUDE.md §12).

Routed here by the supervisor for "add X to my todo", "start the report task",
"mark it done", "archive done", "what's on my list". Parses the message into
``TaskOps`` then runs each op through the ``genie-tasks`` MCP server
(``app.mcp.client.call_tasks_tool``). Its reply is delivered as its own chat
message (``stream=True``), like the greeting.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import SystemMessage

from app.agents.base import AgentResult
from app.agents.events import emit
from app.agents.models import ainvoke, get_chat_model
from app.agents.supervisor.state import GenieState, TaskRecord
from app.agents.task_creator.prompts import TASK_CREATOR_PROMPT
from app.agents.task_creator.schemas import TaskOps
from app.mcp.client import call_tasks_tool

logger = structlog.get_logger(__name__)

_STATUS_LABEL = {"todo": "To Do", "in_progress": "In Progress", "done": "Done"}


async def run_task_creator(state: GenieState, task: TaskRecord) -> AgentResult:  # noqa: ARG001
    user_id = state["user_id"]
    conversation_id = state.get("conversation_id")

    model = get_chat_model(streaming=False, temperature=0).with_structured_output(TaskOps)
    parsed: TaskOps = await ainvoke(
        model, [SystemMessage(content=TASK_CREATOR_PROMPT), *state["messages"]]
    )
    logger.info(
        "task_creator_parsed",
        user_id=user_id,
        ops=[o.action for o in parsed.ops],
    )

    outcomes: list[str] = []
    for op in parsed.ops:
        try:
            outcomes.append(await _run_op(op, user_id, conversation_id))
        except Exception as exc:  # noqa: BLE001 — one bad op must not kill the turn
            logger.warning("task_creator_op_failed", action=op.action, error=str(exc))
            outcomes.append(f"Couldn't complete a task action ({op.action}).")

    reply = (parsed.reply or "").strip()
    detail = "\n".join(f"- {o}" for o in outcomes if o)
    summary = f"{reply}\n\n{detail}".strip() if reply and detail else (reply or detail)
    return AgentResult(summary=summary or "No task changes.", stream=True)


async def _run_op(op, user_id: str, conversation_id: str | None) -> str:
    if op.action == "create":
        if not (op.title or "").strip():
            return "Skipped a task with no title."
        created = await call_tasks_tool(
            "create_task",
            {
                "user_id": user_id,
                "title": op.title.strip(),
                "description": (op.description or None),
                "conversation_id": conversation_id,
            },
        )
        await emit("task_created", {"task": created})
        return f'Added "{created["title"]}" to To Do.'

    if op.action == "move":
        query = (op.target or op.title or "").strip()
        status = op.status or "in_progress"
        match = await call_tasks_tool("find_task", {"user_id": user_id, "query": query})
        if not match:
            return f'Couldn\'t find a task matching "{query}".'
        moved = await call_tasks_tool(
            "set_task_status",
            {"user_id": user_id, "task_id": match["id"], "status": status},
        )
        await emit("task_updated", {"task": moved})
        return f'Moved "{moved["title"]}" to {_STATUS_LABEL.get(status, status)}.'

    if op.action == "summarize":
        target_id = await _resolve_task_id(user_id, op.target, conversation_id)
        if not target_id:
            return "Couldn't find a task to summarise."
        # surface a live "Summarising the task…" pill while the LLM works
        await emit("agent_start", {"agent": "task_summary", "task": "Summarising the task"})
        try:
            t = await call_tasks_tool(
                "summarize_task", {"user_id": user_id, "task_id": target_id}
            )
        finally:
            await emit("agent_end", {"agent": "task_summary", "status": "done"})
        await emit("task_updated", {"task": t})
        return f'Summarised "{t["title"]}" into its description.'

    if op.action == "archive_done":
        count = await call_tasks_tool("archive_done_tasks", {"user_id": user_id})
        await emit("tasks_archived", {"count": count})
        return f"Archived {count} finished task{'s' if count != 1 else ''}."

    if op.action == "list":
        tasks = await call_tasks_tool("list_tasks", {"user_id": user_id})
        if not tasks:
            return "Your task board is empty."
        by_status: dict[str, list[str]] = {}
        for t in tasks:
            by_status.setdefault(t["status"], []).append(t["title"])
        parts = [
            f"{_STATUS_LABEL.get(s, s)}: {', '.join(titles)}"
            for s, titles in by_status.items()
        ]
        return " · ".join(parts)

    return ""


async def _resolve_task_id(
    user_id: str, target: str | None, conversation_id: str | None
) -> str | None:
    """Task id from a fuzzy title, or — if no target — the task tied to this chat."""
    query = (target or "").strip()
    if query:
        match = await call_tasks_tool("find_task", {"user_id": user_id, "query": query})
        return match["id"] if match else None
    tasks = await call_tasks_tool(
        "list_tasks", {"user_id": user_id, "include_archived": True}
    )
    for t in tasks:
        if t.get("conversation_id") == conversation_id:
            return t["id"]
    return None
