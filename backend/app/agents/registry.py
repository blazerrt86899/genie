"""Agent registry (CLAUDE.md §12).

The supervisor routes against THIS registry — its prompt is generated from
``agent_menu()`` and it may only assign tasks to ``KNOWN_AGENTS``. Adding an
agent = add its ``AgentSpec`` here (plus a prompt line, a graph is not needed —
the executor dispatches through the registry).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog

from app.agents.base import AgentResult
from app.agents.greeting.agent import run_greeting
from app.agents.supervisor.state import GenieState, TaskRecord
from app.agents.web_search.agent import run_web_search

logger = structlog.get_logger(__name__)

AgentRunner = Callable[[GenieState, TaskRecord], Awaitable[AgentResult]]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str  # shown to the supervisor LLM
    runner: AgentRunner
    # True → its output is delivered as its own message, not composed by the synthesiser
    stream: bool = False


AGENT_REGISTRY: dict[str, AgentSpec] = {
    "greeting": AgentSpec(
        name="greeting",
        description=(
            "Greets the user with a warm, time-of-day-aware hello. Use whenever "
            "the message contains a greeting or pleasantry (hi, hello, good "
            "morning, how are you, thanks) — even if it also asks for something "
            "else in the same message. Handles ONLY the greeting portion, never "
            "the request itself."
        ),
        runner=run_greeting,
        stream=True,
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


def log_registry() -> None:
    """Log the registered agents — called once from the app lifespan."""
    logger.info(
        "agent_registry_loaded",
        agents=sorted(AGENT_REGISTRY),
        streaming_agents=sorted(n for n, s in AGENT_REGISTRY.items() if s.stream),
    )


def agent_menu() -> str:
    """The registry rendered for the supervisor prompt."""
    return "\n".join(f"- {s.name}: {s.description}" for s in AGENT_REGISTRY.values())
