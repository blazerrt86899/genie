"""Task Creator structured output (CLAUDE.md §12)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TaskAction = Literal["create", "move", "summarize", "archive_done", "list"]
BoardStatus = Literal["todo", "in_progress", "done"]


class TaskOp(BaseModel):
    """One operation the user asked for on their task board."""

    action: TaskAction
    title: str | None = Field(default=None, description="For 'create' — the task title")
    description: str | None = Field(default=None, description="For 'create' — optional details")
    target: str | None = Field(
        default=None,
        description="For 'move' / 'summarize' — words from the title of the existing "
        "task to act on. Leave empty for 'summarize' to mean the task from this chat.",
    )
    status: BoardStatus | None = Field(
        default=None, description="For 'move' — which column to move the task to"
    )


class TaskOps(BaseModel):
    ops: list[TaskOp] = Field(default_factory=list)
    reply: str = Field(
        description="A short, friendly confirmation to show the user (1-2 sentences)"
    )
