"""Task Creator schemas (CLAUDE.md §12)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ExtractedTask(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime | None = None
    priority: int = Field(default=3, ge=1, le=5)
