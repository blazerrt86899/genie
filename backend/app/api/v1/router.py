"""Aggregate v1 router (CLAUDE.md §14)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    conversations,
    documents,
    projects,
    tasks,
    users,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(webhooks.router)
api_router.include_router(users.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(documents.router)
