"""File Creator structured output (CLAUDE.md §12)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FileFormat = Literal["md", "txt", "csv", "json", "docx", "pdf", "xlsx", "code"]


class FileSpec(BaseModel):
    """What file to make, decided from the user's request."""

    filename: str = Field(description="A short, descriptive filename WITHOUT an extension")
    format: FileFormat = Field(
        description=(
            "The target format. 'docx' for a Word document/report/letter, 'pdf' for a "
            "PDF report/one-pager, 'xlsx' for a spreadsheet/table export, 'csv' for raw "
            "tabular data, 'json' for structured data, 'code' for a source file, 'md' "
            "for a Markdown doc/README, 'txt' for plain notes. Default to 'md' when the "
            "request doesn't name a format."
        )
    )
    code_ext: str | None = Field(
        default=None,
        description=(
            "For format='code' only — the file extension without a dot, e.g. 'py', 'ts', 'sql'"
        ),
    )
