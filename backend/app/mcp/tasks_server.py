"""FastMCP server — the task board's CRUD, as MCP tools (CLAUDE.md §12, §22).

Every tool opens its own DB session and delegates to ``app.services.task_service``.
``user_id`` is always an explicit argument (the caller supplies it — the
``task_creator`` agent passes ``GenieState['user_id']``), so this server is
stateless and works both in-process and standalone.

Run standalone (streamable-HTTP) for external MCP clients:
    uv run python -m app.mcp.tasks_server
"""

from __future__ import annotations

import uuid

import structlog
from fastmcp import FastMCP

from app.config import settings
from app.db.session import get_sessionmaker
from app.services import task_service

logger = structlog.get_logger("app.mcp.tasks")

mcp: FastMCP = FastMCP(
    name="genie-tasks",
    instructions=(
        "CRUD for a Genie user's task board. Columns: todo, in_progress, done; "
        "'archived' hides a done task from the board but keeps it. Always pass the "
        "user_id you were given. To act on an existing task by description, call "
        "find_task first to resolve its id."
    ),
)


def _uid(user_id: str) -> uuid.UUID:
    return uuid.UUID(user_id)


@mcp.tool
async def create_task(
    user_id: str,
    title: str,
    description: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Create a task in the To Do column. Returns the created task."""
    logger.info("mcp_create_task", user_id=user_id, conversation_id=conversation_id)
    async with get_sessionmaker()() as db:
        task = await task_service.create_task(
            db,
            _uid(user_id),
            title,
            description=description,
            conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
            source_agent="task_creator",
        )
        return task_service.to_dict(task)


@mcp.tool
async def list_tasks(user_id: str, include_archived: bool = False) -> list[dict]:
    """List the user's tasks (newest first). Archived tasks are excluded unless asked for."""
    async with get_sessionmaker()() as db:
        tasks = await task_service.list_tasks(db, _uid(user_id), include_archived=include_archived)
        logger.info("mcp_list_tasks", user_id=user_id, count=len(tasks))
        return [task_service.to_dict(t) for t in tasks]


@mcp.tool
async def find_task(user_id: str, query: str) -> dict | None:
    """Fuzzy-find one task by text in its title. Returns the task or null."""
    async with get_sessionmaker()() as db:
        task = await task_service.find_task(db, _uid(user_id), query)
        return task_service.to_dict(task) if task else None


@mcp.tool
async def set_task_status(user_id: str, task_id: str, status: str) -> dict:
    """Move a task. status = todo | in_progress | done | archived."""
    logger.info("mcp_set_task_status", user_id=user_id, task_id=task_id, status=status)
    async with get_sessionmaker()() as db:
        task = await task_service.move_task(db, _uid(user_id), uuid.UUID(task_id), status)
        return task_service.to_dict(task)


@mcp.tool
async def update_task(
    user_id: str, task_id: str, title: str | None = None, description: str | None = None
) -> dict:
    """Edit a task's title and/or description."""
    async with get_sessionmaker()() as db:
        task = await task_service.update_details(
            db, _uid(user_id), uuid.UUID(task_id), title=title, description=description
        )
        return task_service.to_dict(task)


@mcp.tool
async def delete_task(user_id: str, task_id: str) -> bool:
    """Permanently delete a task. Returns True."""
    logger.info("mcp_delete_task", user_id=user_id, task_id=task_id)
    async with get_sessionmaker()() as db:
        await task_service.delete_task(db, _uid(user_id), uuid.UUID(task_id))
        return True


@mcp.tool
async def archive_done_tasks(user_id: str) -> int:
    """Move every 'done' task to 'archived'. Returns how many were archived."""
    async with get_sessionmaker()() as db:
        count = await task_service.archive_done(db, _uid(user_id))
        logger.info("mcp_archive_done_tasks", user_id=user_id, archived=count)
        return count


def main() -> None:
    host = settings.TASKS_MCP_HOST
    port = settings.TASKS_MCP_PORT
    logger.info("tasks_mcp_serving", host=host, port=port, transport="streamable-http")
    mcp.run(transport="streamable-http", host=host, port=port, show_banner=False)


if __name__ == "__main__":
    from app.core.logging import configure_logging

    configure_logging()
    main()
