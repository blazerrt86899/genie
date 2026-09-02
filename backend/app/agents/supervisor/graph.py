"""LangGraph graph assembly (CLAUDE.md §9).

    START → prompt_enhancer → supervisor → executor → synthesiser → validator → {supervisor | END}

The compiled graph + ``AsyncPostgresSaver`` checkpointer (session-mode URL) are
built once in the FastAPI lifespan and held via ``set_runtime_graph()``.
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.guardrails import input_guard_node
from app.agents.prompt_enhancer.agent import prompt_enhancer_node
from app.agents.supervisor.nodes import (
    cache_lookup_node,
    executor_node,
    retriever_node,
    route_after_cache,
    route_after_validator,
    supervisor_node,
    synthesiser_node,
    validator_node,
)
from app.agents.supervisor.state import GenieState

logger = structlog.get_logger(__name__)


def build_graph() -> StateGraph:
    nodes = [
        "input_guard", "prompt_enhancer", "cache_lookup", "retriever",
        "supervisor", "executor", "synthesiser", "validator",
    ]
    logger.info(
        "graph_build",
        nodes=nodes,
        flow="START→input_guard→prompt_enhancer→cache_lookup→{END|retriever→supervisor→executor→synthesiser→validator→{supervisor|END}}",
    )
    graph = StateGraph(GenieState)
    graph.add_node("input_guard", input_guard_node)  # redact secrets/PII before any LLM
    graph.add_node("prompt_enhancer", prompt_enhancer_node)
    graph.add_node("cache_lookup", cache_lookup_node)  # semantic response cache (§ caching)
    graph.add_node("retriever", retriever_node)  # project Knowledge Base (§10)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("executor", executor_node)
    graph.add_node("synthesiser", synthesiser_node)
    graph.add_node("validator", validator_node)

    graph.add_edge(START, "input_guard")
    graph.add_edge("input_guard", "prompt_enhancer")
    graph.add_edge("prompt_enhancer", "cache_lookup")
    graph.add_conditional_edges(
        "cache_lookup", route_after_cache, {"retriever": "retriever", END: END}
    )
    graph.add_edge("retriever", "supervisor")
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
    logger.info(
        "runtime_graph_set",
        checkpointed=getattr(compiled, "checkpointer", None) is not None,
    )


def get_runtime_graph() -> Any:
    if _runtime_graph is None:
        raise RuntimeError("graph not compiled — is the app lifespan running?")
    return _runtime_graph
