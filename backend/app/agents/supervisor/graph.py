"""LangGraph supervisor graph assembly — STUB (Phase 1, CLAUDE.md §9).

The checkpointer ALWAYS uses ``DATABASE_URL_SESSION`` (Supavisor session mode —
needs LISTEN/NOTIFY). ``interrupt_before=["calendar"]`` for write confirmation.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.calendar.agent import calendar_node
from app.agents.prompt_enhancer.agent import prompt_enhancer_node
from app.agents.rag.agent import rag_node
from app.agents.supervisor.nodes import (
    route_to_agents,
    should_continue_or_end,
    supervisor_node,
    synthesiser_node,
)
from app.agents.supervisor.state import GenieState
from app.agents.task_creator.agent import task_creator_node
from app.agents.web_search.agent import web_search_node

_AGENT_NODES = {
    "prompt_enhancer": prompt_enhancer_node,
    "web_search": web_search_node,
    "rag": rag_node,
    "calendar": calendar_node,
    "task_creator": task_creator_node,
}


def build_graph() -> StateGraph:
    graph = StateGraph(GenieState)
    graph.add_node("supervisor", supervisor_node)
    for name, node in _AGENT_NODES.items():
        graph.add_node(name, node)
    graph.add_node("synthesiser", synthesiser_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_to_agents)
    for name in _AGENT_NODES:
        graph.add_edge(name, "synthesiser")
    graph.add_conditional_edges(
        "synthesiser", should_continue_or_end, {"continue": "supervisor", END: END}
    )
    return graph


async def compile_graph(checkpointer: Any = None):
    """Compile the graph with the Postgres checkpointer. Wired in Phase 1."""
    raise NotImplementedError("Phase 1")
