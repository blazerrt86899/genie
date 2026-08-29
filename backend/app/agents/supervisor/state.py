"""GenieState + RouteDecision (CLAUDE.md §9)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

AgentName = Literal[
    "prompt_enhancer",
    "web_search",
    "rag",
    "calendar",
    "task_creator",
]


class GenieState(TypedDict):
    messages: Annotated[list, add_messages]  # append-only
    user_id: str
    conversation_id: str
    intent: str | None
    active_agents: list[str]
    intermediate_results: dict[str, Any]  # keyed by agent name
    final_response: str | None
    token_usage: dict[str, int]  # {"total": N, "by_agent": {...}}
    user_memories: list[dict]
    should_interrupt: bool
    metadata: dict[str, Any]


class RouteDecision(BaseModel):
    """Structured output the supervisor LLM must produce (CLAUDE.md §4.1)."""

    agents: list[AgentName]
    rationale: str = Field(description="Why the supervisor chose these agents")
    parallel: bool = Field(default=True, description="Run agents concurrently when True")
    requires_confirmation: bool = Field(
        default=False, description="True for calendar writes / external side effects"
    )
