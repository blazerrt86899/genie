"""LangGraph graph assembly (CLAUDE.md §9).

    START → supervisor → executor → synthesiser → validator → {supervisor | END}

The compiled graph + ``AsyncPostgresSaver`` checkpointer (session-mode URL) are
built once in the FastAPI lifespan and held via ``set_runtime_graph()``.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.supervisor.nodes import (
    executor_node,
    route_after_validator,
    supervisor_node,
    synthesiser_node,
    validator_node,
)
from app.agents.supervisor.state import GenieState


def build_graph() -> StateGraph:
    graph = StateGraph(GenieState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("executor", executor_node)
    graph.add_node("synthesiser", synthesiser_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "executor")
    graph.add_edge("executor", "synthesiser")
    graph.add_edge("synthesiser", "validator")
    graph.add_conditional_edges(
        "validator", route_after_validator, {"supervisor": "supervisor", END: END}
    )
    return graph


_runtime_graph: Any = None


def set_runtime_graph(compiled: Any) -> None:
    """Called once from the FastAPI lifespan with the compiled+checkpointed graph."""
    global _runtime_graph
    _runtime_graph = compiled


def get_runtime_graph() -> Any:
    if _runtime_graph is None:
        raise RuntimeError("graph not compiled — is the app lifespan running?")
    return _runtime_graph
