"""Graph nodes (CLAUDE.md §9).

`chat_node` is the interim single-node chatbot; the supervisor / synthesiser
nodes below stay stubbed until the agent layer lands.
"""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from app.agents.supervisor.prompts import CHAT_SYSTEM_PROMPT
from app.agents.supervisor.state import GenieState, RouteDecision
from app.config import settings


def get_chat_model() -> ChatOpenAI:
    """The chat LLM — pinned model from settings (CLAUDE.md §3)."""
    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        temperature=0.7,
        streaming=True,
        api_key=settings.OPENAI_API_KEY,
    )


async def chat_node(state: GenieState) -> dict:
    """Single-node chat: prepend the system prompt (+ project instructions when
    the chat belongs to a project), call the model.

    Token streaming is surfaced by ``graph.astream_events(version="v2")`` at the
    call site — see ``app.services.chat_service``.
    """
    system = CHAT_SYSTEM_PROMPT
    instructions = state.get("project_instructions")
    if instructions:
        system = (
            f"{CHAT_SYSTEM_PROMPT}\n\n---\n"
            f"Project instructions (follow these for this conversation):\n{instructions}"
        )

    model = get_chat_model()
    messages = [SystemMessage(content=system), *state["messages"]]
    response = await model.ainvoke(messages)
    return {"messages": [response]}


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
    "chat_node",
    "get_chat_model",
    "supervisor_node",
    "route_to_agents",
    "synthesiser_node",
    "should_continue_or_end",
    "RouteDecision",
]
