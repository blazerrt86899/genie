"""Task endpoints (CLAUDE.md §14). STUB (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.clerk import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(
    status: str | None = None,
    date: str | None = None,
    user: User = Depends(get_current_user),
):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.patch("/{task_id}")
async def update_task(task_id: str, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Not implemented yet (Phase 2)")
