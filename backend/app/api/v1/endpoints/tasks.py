"""Task board endpoints (CLAUDE.md §14). All owned by ``get_current_user``.

Chat-driven moves go through the ``task_creator`` agent → the tasks MCP; these
endpoints back the board UI (list, drag, the detail modal, the "Archive done"
button).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clerk import get_current_user
from app.core.exceptions import GenieError
from app.db.models.task import Task
from app.db.models.user import User
from app.db.session import get_db
from app.services import task_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    status: str
    conversation_id: str | None
    source_agent: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: str | None = None


class ArchiveResult(BaseModel):
    archived: int


def _out(t: Task) -> TaskOut:
    return TaskOut(
        id=str(t.id),
        title=t.title,
        description=t.description,
        status=t.status,
        conversation_id=str(t.conversation_id) if t.conversation_id else None,
        source_agent=t.source_agent,
        created_at=t.created_at,
        updated_at=t.updated_at,
        archived_at=t.archived_at,
    )


def _uuid_or_404(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    include_archived: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TaskOut]:
    tasks = await task_service.list_tasks(db, user.id, include_archived=include_archived)
    logger.info("tasks_list", user_id=str(user.id), count=len(tasks))
    return [_out(t) for t in tasks]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    task = await task_service.create_task(
        db, user.id, body.title, description=body.description, source_agent="api"
    )
    return _out(task)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    try:
        task = await task_service.get_task(db, user.id, _uuid_or_404(task_id))
    except GenieError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _out(task)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(
    task_id: str,
    body: TaskPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TaskOut:
    tid = _uuid_or_404(task_id)
    logger.info(
        "tasks_patch",
        user_id=str(user.id),
        task_id=task_id,
        fields=[k for k, v in body.model_dump(exclude_unset=True).items()],
    )
    try:
        if body.status is not None:
            await task_service.move_task(db, user.id, tid, body.status)
        if body.title is not None or body.description is not None:
            await task_service.update_details(
                db, user.id, tid, title=body.title, description=body.description
            )
        task = await task_service.get_task(db, user.id, tid)
    except GenieError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _out(task)


@router.post("/archive-done", response_model=ArchiveResult)
async def archive_done(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchiveResult:
    count = await task_service.archive_done(db, user.id)
    logger.info("tasks_archive_done_endpoint", user_id=str(user.id), archived=count)
    return ArchiveResult(archived=count)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await task_service.delete_task(db, user.id, _uuid_or_404(task_id))
    except GenieError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return Response(status_code=204)
