"""Project endpoints (CLAUDE.md §14, §15).

A project is a named workspace whose ``instructions`` are prepended to the system
prompt for every chat inside it. Deleting a project cascades to its chats.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor.graph import get_runtime_graph
from app.api.v1.endpoints.conversations import ConversationSummary, conversation_summary
from app.core.clerk import get_current_user
from app.db.models.user import User
from app.db.repositories.conversation_repo import ConversationRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.project_repo import ProjectRepository
from app.db.session import get_db
from app.schemas.rag import RagSettings
from app.schemas.rag import resolve as resolve_rag

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    instructions: str | None = None
    rag_settings: dict | None = None  # merged into the stored dict


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    instructions: str | None
    rag_settings: dict
    document_count: int
    rag_locked: bool  # embedding model can't change once a document exists
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectOut):
    conversation_count: int


class ProjectDetail(ProjectOut):
    conversations: list[ConversationSummary]


def _out(p, document_count: int = 0) -> ProjectOut:
    return ProjectOut(
        id=str(p.id),
        name=p.name,
        description=p.description,
        instructions=p.instructions,
        rag_settings=resolve_rag(p.rag_settings).model_dump(mode="json"),
        document_count=document_count,
        rag_locked=document_count > 0,
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
    doc_count = await DocumentRepository(db).count_for_project(pid)
    return ProjectDetail(
        **_out(project, doc_count).model_dump(),
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
    repo = ProjectRepository(db)
    project = await repo.get_for_user(pid, user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    fields = body.model_dump(exclude_unset=True)
    doc_count = await DocumentRepository(db).count_for_project(pid)

    if body.rag_settings is not None:
        merged = {**(project.rag_settings or {}), **body.rag_settings}
        current = resolve_rag(project.rag_settings)
        candidate = RagSettings(**merged)  # validate / clamp
        if doc_count > 0 and candidate.embedding_model != current.embedding_model:
            raise HTTPException(
                status_code=409,
                detail="embedding model is locked once the project has documents",
            )
        fields["rag_settings"] = candidate.model_dump(mode="json")

    updated = await repo.update(pid, user.id, **fields)
    return _out(updated, doc_count)


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
    logger.info(
        "project_delete_cascade",
        project_id=project_id,
        user_id=str(user.id),
        conversations=len(thread_ids),
    )
    await repo.delete_for_user(pid, user.id)  # cascades conversations + messages

    for tid in thread_ids:  # best-effort — orphan checkpoint rows are harmless
        try:
            await get_runtime_graph().checkpointer.adelete_thread(tid)
        except Exception:  # noqa: BLE001
            logger.warning("checkpointer_thread_delete_failed", conversation_id=tid)
    return Response(status_code=204)
