"""Task board logic — the single place task operations live (CLAUDE.md §12, §22).

Every caller — the REST endpoints, the FastMCP task tools (`app/mcp/tasks_server`),
and tests — goes through here. Each function takes an ``AsyncSession``; the MCP
tools open their own via ``get_sessionmaker()``.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import GenieError, NotFoundError
from app.core.logging import preview
from app.db.models.task import TASK_STATUSES, Task
from app.db.repositories.message_repo import MessageRepository
from app.db.repositories.task_repo import TaskRepository

logger = structlog.get_logger(__name__)

_SUMMARY_SYSTEM = (
    "You summarise a task's discussion. Given the task title and the chat "
    "transcript it was created in, write a 3-4 line summary of what the task is "
    "about and any decisions / details agreed. Plain prose, no preamble, no "
    "bullet list, no markdown headings."
)
_TRANSCRIPT_CHARS = 8000


class TaskValidationError(GenieError):
    """A task field failed validation."""

    status_code = 422
    code = "task_invalid"


def _check_status(status: str) -> str:
    if status not in TASK_STATUSES:
        raise TaskValidationError(
            f"unknown status '{status}' (allowed: {sorted(TASK_STATUSES)})"
        )
    return status


async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    *,
    description: str | None = None,
    conversation_id: uuid.UUID | None = None,
    source_agent: str | None = None,
) -> Task:
    title = (title or "").strip()
    if not title:
        raise TaskValidationError("task title must not be empty")
    logger.info(
        "task_service_create",
        user_id=str(user_id),
        title=preview(title, 120),
        via=source_agent or "api",
    )
    return await TaskRepository(db).create(
        user_id,
        title,
        description=description,
        conversation_id=conversation_id,
        source_agent=source_agent,
    )


async def list_tasks(
    db: AsyncSession, user_id: uuid.UUID, *, include_archived: bool = False
) -> list[Task]:
    return await TaskRepository(db).list_for_user(user_id, include_archived=include_archived)


async def get_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await TaskRepository(db).get_for_user(task_id, user_id)
    if task is None:
        raise NotFoundError("task not found")
    return task


async def find_task(db: AsyncSession, user_id: uuid.UUID, query: str) -> Task | None:
    return await TaskRepository(db).find_by_title(user_id, query)


async def move_task(
    db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, status: str
) -> Task:
    _check_status(status)
    logger.info("task_service_move", user_id=str(user_id), task_id=str(task_id), status=status)
    task = await TaskRepository(db).set_status(task_id, user_id, status)
    if task is None:
        raise NotFoundError("task not found")
    return task


async def update_details(
    db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, **fields: str | None
) -> Task:
    """``fields`` may contain ``title`` and/or ``description`` — only the keys
    actually passed are applied (``description`` can be set to ``None`` to clear)."""
    logger.info(
        "task_service_update_details",
        user_id=str(user_id),
        task_id=str(task_id),
        fields=sorted(fields),
    )
    task = await TaskRepository(db).update(task_id, user_id, **fields)
    if task is None:
        raise NotFoundError("task not found")
    return task


async def summarize_task(
    db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> Task:
    """Summarise the task's linked chat into 3-4 lines → the task description."""
    task = await get_task(db, user_id, task_id)
    if task.conversation_id is None:
        raise TaskValidationError("this task has no linked chat to summarise")

    messages = await MessageRepository(db).list_for_conversation(task.conversation_id, limit=100)
    if not messages:
        raise TaskValidationError("the linked chat has no messages yet")

    transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)[:_TRANSCRIPT_CHARS]
    logger.info(
        "task_service_summarize",
        user_id=str(user_id),
        task_id=str(task_id),
        conversation_id=str(task.conversation_id),
        messages=len(messages),
    )

    summary = await _summarise(task.title, transcript)
    logger.info("task_summary_generated", task_id=str(task_id), chars=len(summary))
    return await update_details(db, user_id, task_id, description=summary)


async def _summarise(title: str, transcript: str) -> str:
    """3-4 line summary of a task's chat. Isolated so tests can stub the LLM."""
    if not settings.llm_configured:
        raise TaskValidationError("summarisation needs OPENAI_API_KEY")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        temperature=0.3,
        streaming=False,
        max_tokens=200,
        api_key=settings.OPENAI_API_KEY,
    )
    resp = await model.ainvoke(
        [
            SystemMessage(content=_SUMMARY_SYSTEM),
            HumanMessage(content=f"Task: {title}\n\nTranscript:\n{transcript}"),
        ]
    )
    return str(resp.content).strip()


async def archive_done(db: AsyncSession, user_id: uuid.UUID) -> int:
    logger.info("task_service_archive_done", user_id=str(user_id))
    return await TaskRepository(db).archive_done(user_id)


async def delete_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    logger.info("task_service_delete", user_id=str(user_id), task_id=str(task_id))
    if not await TaskRepository(db).delete_for_user(task_id, user_id):
        raise NotFoundError("task not found")


def to_dict(task: Task) -> dict:
    """Serialisable view — used by the MCP tools and the SSE frames."""
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "conversation_id": str(task.conversation_id) if task.conversation_id else None,
        "source_agent": task.source_agent,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "archived_at": task.archived_at.isoformat() if task.archived_at else None,
    }
