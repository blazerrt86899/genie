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
    """

    summary: str
    detail: str | None = None
    sources: list[dict] = field(default_factory=list)
