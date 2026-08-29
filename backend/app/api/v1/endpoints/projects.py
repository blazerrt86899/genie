"""Project endpoints (CLAUDE.md §14, §15).

A project is a named workspace whose ``instructions`` are prepended to the system
prompt for every chat inside it. Deleting a project cascades to its chats.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor.graph import get_runtime_graph
from app.api.v1.endpoints.conversations import ConversationSummary, conversation_summary
from app.core.clerk import get_current_user
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.project_repo import ProjectRepository
from app.db.session import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    instructions: str | None
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectOut):
    conversation_count: int


class ProjectDetail(ProjectOut):
    conversations: list[ConversationSummary]


def _out(p) -> ProjectOut:
    return ProjectOut(
        id=str(p.id),
        name=p.name,
        description=p.description,
        instructions=p.instructions,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _uuid_or_404(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    project = await ProjectRepository(db).create(
        user.id, body.name.strip(), body.description, body.instructions
    )
    return _out(project)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    rows = await ProjectRepository(db).list_for_user(user.id)
    return [
        ProjectSummary(**_out(p).model_dump(), conversation_count=count)
        for p, count in rows
    ]


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    pid = _uuid_or_404(project_id)
    project = await ProjectRepository(db).get_for_user(pid, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    convs = await ConversationRepository(db).list_for_project(pid, user.id)
    return ProjectDetail(
        **_out(project).model_dump(),
        conversations=[conversation_summary(c) for c in convs],
    )


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectOut:
    pid = _uuid_or_404(project_id)
    updated = await ProjectRepository(db).update(
        pid, user.id, **body.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="project not found")
    return _out(updated)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    pid = _uuid_or_404(project_id)
    repo = ProjectRepository(db)
    if await repo.get_for_user(pid, user.id) is None:
        raise HTTPException(status_code=404, detail="project not found")

    thread_ids = [
        str(c.id) for c in await ConversationRepository(db).list_for_project(pid, user.id)
    ]
    await repo.delete_for_user(pid, user.id)  # cascades conversations + messages

    for tid in thread_ids:  # best-effort — orphan checkpoint rows are harmless
        try:
            await get_runtime_graph().checkpointer.adelete_thread(tid)
        except Exception:  # noqa: BLE001
            pass
    return Response(status_code=204)
