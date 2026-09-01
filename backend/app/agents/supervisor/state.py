"""GenieState + the supervisor's planning models (CLAUDE.md §9)."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

TaskStatus = Literal["pending", "in_progress", "done", "failed"]


class TaskRecord(TypedDict):
    """One row of the supervisor's task ledger.

    The supervisor writes these; the executor flips ``status`` as it runs each
    agent and fills ``result`` / ``error``.
    """

    id: str  # "t1", "t2", …
    description: str  # what this step should accomplish
    agent: str  # registry key of the agent assigned to it
    status: TaskStatus
    depends_on: list[str]  # ids of tasks that must be "done" first
    result: str | None  # the agent's summary once done
    error: str | None


class GenieState(TypedDict):
    messages: Annotated[list, add_messages]  # append-only
    user_id: str
    conversation_id: str
    project_instructions: str | None  # prepended to the system prompt when set
    client_hour: int | None  # the user's local hour (0-23), for time-aware agents
    model: str | None  # picked chat-model id (MODEL_CATALOG); None → server default
    attachments: list[dict]  # [{filename, kind, text}] — files sent with THIS turn only
    rag_settings: dict | None  # the project's RagSettings (§10); None outside a KB project
    has_kb: bool  # the project has >=1 ready document
    needs_documents: bool  # the enhancer's gate for running retrieval this turn
    retrieved_chunks: list[dict]  # [{content, similarity, heading, filename}] from the KB
    intent: str | None  # short label from the prompt_enhancer
    enhanced_query: str | None  # the latest message rewritten self-contained (prompt_enhancer)
    plan: list[TaskRecord]  # the task ledger — supervisor writes, executor updates
    supervisor_turns: int  # how many times the supervisor has planned this run
    active_agents: list[str]  # currently running (surfaced to the UI)
    intermediate_results: dict[str, Any]  # {task_id: {agent, summary, detail, sources, streamed}}
    streamed_segments: list[str]  # agent outputs already shown to the user, in order
    final_response: str | None
    validation: dict[str, Any] | None  # {"approved": bool, "issues": [...]}
    token_usage: dict[str, int]  # {"total": N, "by_agent": {...}}
    user_memories: list[dict]
    should_interrupt: bool
    metadata: dict[str, Any]


# ─── Supervisor structured output ─────────────────────────────────────────────


class PlanStep(BaseModel):
    """One step the supervisor wants run. Routing is ALWAYS the LLM's call here —
    never hardcoded ``if "search" in query`` logic (CLAUDE.md §4.1)."""

    description: str = Field(description="What this step should accomplish, in one sentence")
    agent: str = Field(description="The agent to run this step (must be one offered in the prompt)")
    depends_on: list[int] = Field(
        default_factory=list,
        description="1-based positions of earlier steps whose output this step needs",
    )


class SupervisorPlan(BaseModel):
    steps: list[PlanStep] = Field(
        default_factory=list,
        description="Ordered plan. Empty when no specialist agent is needed — "
        "the answer will then be written directly.",
    )
    rationale: str = Field(description="Why this plan (or why no agents are needed)")


class Validation(BaseModel):
    """Validator verdict — the synthesised reply passed a grounding / sanity check."""

    approved: bool
    issues: list[str] = Field(default_factory=list)


class EnhancedPrompt(BaseModel):
    """Prompt-enhancer output: a self-contained rewrite of the user's latest
    message plus a short intent label. Never answers the request."""

    intent: str = Field(description="A 2-4 word label for what the user wants")
    enhanced_query: str = Field(
        description="The latest message rewritten as a precise, self-contained request "
        "(resolve pronouns / references using the conversation). Do NOT answer it."
    )
    needs_documents: bool = Field(
        default=False,
        description="True if answering well would need the user's project documents / "
        "knowledge base (a real question about a topic, code, a doc). False for "
        "greetings, thanks, small talk, or tasks about the task board.",
    )
