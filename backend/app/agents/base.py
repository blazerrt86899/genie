"""Shared agent types (CLAUDE.md §12).

Kept in its own module so ``registry.py`` and the individual agents can both
import ``AgentResult`` without a circular import.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentResult:
    """What every registered agent returns.

    ``summary`` is the concise, user-relevant outcome — it lands on the task
    ledger (``TaskRecord.result``) and is handed to the synthesiser. ``detail``
    is optional longer context; ``sources`` are ``{"title", "url"}`` dicts the
    synthesiser can cite.

    ``stream=True`` means the summary is already user-ready and should be shown
    to the user the moment this step finishes (before later steps run) — the
    synthesiser then composes only the remaining, non-streamed findings and does
    not repeat it. Use for short, final outputs like a greeting.

    ``files`` are downloadable files this step produced (the ``file_creator``
    agent) — ``{"id", "filename", "mime_type", "byte_size", "summary"}`` dicts,
    surfaced the same way ``sources`` are: collected across the turn and sent as
    one SSE event before ``done``.
    """

    summary: str
    detail: str | None = None
    sources: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    stream: bool = False
