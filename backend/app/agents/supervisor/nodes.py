"""Supervisor + synthesiser graph nodes — STUB (Phase 1, CLAUDE.md §9)."""

from __future__ import annotations

from app.agents.supervisor.state import GenieState, RouteDecision


async def supervisor_node(state: GenieState) -> GenieState:
    """LLM routing via ``ChatOpenAI.with_structured_output(RouteDecision)``.

    Also enforces the token budget (CLAUDE.md §4.6): checks ``state['token_usage']``
    before routing to additional agents.
    """
    raise NotImplementedError("Phase 1")


def route_to_agents(state: GenieState) -> list[str]:
    """Conditional-edge function — returns the agent node names to fan out to."""
    raise NotImplementedError("Phase 1")


async def synthesiser_node(state: GenieState) -> GenieState:
    """Merge ``state['intermediate_results']`` into ``final_response``."""
    raise NotImplementedError("Phase 1")


def should_continue_or_end(state: GenieState) -> str:
    """Conditional-edge function after the synthesiser — 'continue' or END."""
    raise NotImplementedError("Phase 1")


__all__ = [
    "supervisor_node",
    "route_to_agents",
    "synthesiser_node",
    "should_continue_or_end",
    "RouteDecision",
]
