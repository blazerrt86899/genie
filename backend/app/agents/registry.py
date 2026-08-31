"""Agent registry (CLAUDE.md §12).

The supervisor routes against THIS registry — its prompt is generated from
``agent_menu()`` and it may only assign tasks to ``KNOWN_AGENTS``. Adding an
agent = add its ``AgentSpec`` here (plus a prompt line, a graph is not needed —
the executor dispatches through the registry).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agents.base import AgentResult
from app.agents.greeting.agent import run_greeting
from app.agents.supervisor.state import GenieState, TaskRecord
from app.agents.web_search.agent import run_web_search

AgentRunner = Callable[[GenieState, TaskRecord], Awaitable[AgentResult]]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str  # shown to the supervisor LLM
    runner: AgentRunner


AGENT_REGISTRY: dict[str, AgentSpec] = {
    "greeting": AgentSpec(
        name="greeting",
        description=(
            "Greets the user with a warm, time-of-day-aware hello. Use for any "
            "message that is primarily a greeting or small talk (hi, hello, good "
            "morning, how are you). Handles ONLY the greeting."
        ),
        runner=run_greeting,
    ),
    "web_search": AgentSpec(
        name="web_search",
        description=(
            "Searches the live web via Tavily and returns a grounded summary with "
            "sources. Use for current events, recent facts, prices, people, "
            "anything needing up-to-date or external information."
        ),
        runner=run_web_search,
    ),
}

KNOWN_AGENTS: frozenset[str] = frozenset(AGENT_REGISTRY)


def agent_menu() -> str:
    """The registry rendered for the supervisor prompt."""
    return "\n".join(f"- {s.name}: {s.description}" for s in AGENT_REGISTRY.values())
