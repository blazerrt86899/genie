"""Graph nodes (CLAUDE.md §9).

    START → supervisor → executor → synthesiser → validator → {supervisor | END}

- supervisor:  LLM planning via ``with_structured_output(SupervisorPlan)`` → a
               task ledger. Never hardcoded routing (CLAUDE.md §4.1).
- executor:    walks the ledger, runs each agent through the registry in
               dependency order, flips ``status`` and records results.
- synthesiser: composes the single user-facing reply (the only node whose tokens
               stream to the client).
- validator:   minimal for now — approves any non-empty answer; a real content
               check comes later.
"""

from __future__ import annotations

import structlog
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END

from app.agents.models import get_chat_model
from app.agents.registry import AGENT_REGISTRY, KNOWN_AGENTS, agent_menu
from app.agents.supervisor.prompts import (
    CHAT_SYSTEM_PROMPT,
    LEDGER_PREFACE,
    SUPERVISOR_SYSTEM_PROMPT,
    SYNTHESISER_SYSTEM_PROMPT,
)
from app.agents.supervisor.state import (
    GenieState,
    PlanStep,
    SupervisorPlan,
    TaskRecord,
)
from app.config import settings

logger = structlog.get_logger(__name__)


# ─── shared helpers ──────────────────────────────────────────────────────────


async def _emit(name: str, data: dict) -> None:
    """Dispatch a custom event (surfaces in ``astream_events`` as ``on_custom_event``).

    Swallows the error when there is no callback manager — e.g. a unit test
    calling the node directly.
    """
    try:
        await adispatch_custom_event(name, data)
    except Exception:  # noqa: BLE001
        pass


def _ledger_text(plan: list[TaskRecord]) -> str:
    if not plan:
        return ""
    body = "\n".join(
        f"- [{t['status']}] {t['agent']}: {t['description']}"
        + (f" → {t['result']}" if t.get("result") else "")
        for t in plan
    )
    return LEDGER_PREFACE.format(ledger_body=body)


def _plan_to_ledger(steps: list[PlanStep]) -> list[TaskRecord]:
    """Validate the LLM's plan → an executable ledger.

    Drops steps for unknown agents and any repeat of an agent already in the
    plan (CLAUDE.md §16), then remaps 1-based ``depends_on`` positions to the
    surviving task ids.
    """
    kept: list[tuple[int, PlanStep]] = []
    seen: set[str] = set()
    for idx, step in enumerate(steps, start=1):
        if step.agent not in KNOWN_AGENTS or step.agent in seen:
            continue
        seen.add(step.agent)
        kept.append((idx, step))

    orig_to_id = {orig: f"t{n}" for n, (orig, _) in enumerate(kept, start=1)}
    ledger: list[TaskRecord] = []
    for n, (orig, step) in enumerate(kept, start=1):
        deps = [orig_to_id[d] for d in step.depends_on if d in orig_to_id and d != orig]
        ledger.append(
            TaskRecord(
                id=f"t{n}",
                description=step.description.strip() or step.agent,
                agent=step.agent,
                status="pending",
                depends_on=deps,
                result=None,
                error=None,
            )
        )
    return ledger


def _format_findings(results: dict) -> str:
    blocks: list[str] = []
    for agent, r in results.items():
        block = f"## {agent}\n{r.get('summary', '')}"
        sources = r.get("sources") or []
        if sources:
            block += "\n\nSources:\n" + "\n".join(
                f"[{i}] {s.get('title', '')} — {s.get('url', '')}"
                for i, s in enumerate(sources, start=1)
            )
        blocks.append(block)
    return "\n\n".join(blocks)


# ─── nodes ───────────────────────────────────────────────────────────────────


async def supervisor_node(state: GenieState) -> dict:
    turns = state.get("supervisor_turns", 0)
    usage = state.get("token_usage") or {}
    if usage.get("total", 0) >= settings.MAX_TOKENS_PER_RUN:
        logger.warning("token_budget_exhausted", total=usage.get("total"))
        return {"plan": [], "supervisor_turns": turns + 1, "intent": "token budget reached"}

    system = SUPERVISOR_SYSTEM_PROMPT.format(
        agent_menu=agent_menu(),
        ledger=_ledger_text(state.get("plan") or []) if turns else "",
    )
    if state.get("project_instructions"):
        system += f"\n\nProject instructions to respect:\n{state['project_instructions']}"

    model = get_chat_model(streaming=False, temperature=0).with_structured_output(SupervisorPlan)
    try:
        plan_out: SupervisorPlan = await model.ainvoke(
            [SystemMessage(content=system), *state["messages"]]
        )
    except Exception:  # noqa: BLE001
        logger.warning("supervisor_plan_failed", exc_info=True)
        return {
            "plan": [],
            "supervisor_turns": turns + 1,
            "intent": "planning failed — answering directly",
        }

    ledger = _plan_to_ledger(plan_out.steps)
    logger.info("supervisor_planned", agents=[t["agent"] for t in ledger], turn=turns + 1)
    return {"plan": ledger, "supervisor_turns": turns + 1, "intent": plan_out.rationale}


async def executor_node(state: GenieState) -> dict:
    plan: list[TaskRecord] = [dict(t) for t in (state.get("plan") or [])]  # type: ignore[misc]
    results = dict(state.get("intermediate_results") or {})
    if not plan:
        return {"plan": plan, "intermediate_results": results, "active_agents": []}

    # A live view so a later agent can read an earlier one's ledger + results.
    state = {**state, "plan": plan, "intermediate_results": results}
    done = {t["id"] for t in plan if t["status"] == "done"}
    progressed = True
    while progressed:
        progressed = False
        for task in plan:
            if task["status"] != "pending" or not set(task["depends_on"]) <= done:
                continue
            progressed = True
            spec = AGENT_REGISTRY.get(task["agent"])
            task["status"] = "in_progress"
            await _emit("agent_start", {"agent": task["agent"], "task": task["description"]})
            try:
                if spec is None:
                    raise RuntimeError(f"unknown agent '{task['agent']}'")
                res = await spec.runner(state, task)  # type: ignore[arg-type]
                task["status"] = "done"
                task["result"] = res.summary
                results[task["agent"]] = {
                    "summary": res.summary,
                    "detail": res.detail,
                    "sources": res.sources,
                }
                done.add(task["id"])
            except Exception as exc:  # noqa: BLE001
                task["status"] = "failed"
                task["error"] = str(exc)
                logger.warning("agent_failed", agent=task["agent"], error=str(exc))
            await _emit("agent_end", {"agent": task["agent"], "status": task["status"]})

    await _emit("plan", {"steps": plan})
    return {"plan": plan, "intermediate_results": results, "active_agents": []}


async def synthesiser_node(state: GenieState) -> dict:
    plan = state.get("plan") or []
    results = state.get("intermediate_results") or {}

    # Fast path: a pure greeting — relay it verbatim, no LLM round-trip.
    if (
        len(plan) == 1
        and plan[0]["agent"] == "greeting"
        and plan[0]["status"] == "done"
        and plan[0].get("result")
    ):
        text = str(plan[0]["result"])
        return {"messages": [AIMessage(content=text)], "final_response": text}

    system = SYNTHESISER_SYSTEM_PROMPT if results else CHAT_SYSTEM_PROMPT
    if state.get("project_instructions"):
        system += f"\n\n---\nProject instructions (follow these):\n{state['project_instructions']}"

    convo = list(state["messages"])
    if results:
        convo.append(SystemMessage(content="Agent findings:\n" + _format_findings(results)))

    model = get_chat_model(streaming=True)
    resp = await model.ainvoke([SystemMessage(content=system), *convo])
    return {"messages": [resp], "final_response": str(resp.content)}


async def validator_node(state: GenieState) -> dict:
    """Minimal gate — approve any non-empty answer. A real content check (LLM
    ``with_structured_output(Validation)``) lands here next."""
    messages = state.get("messages") or []
    answer = str(messages[-1].content).strip() if messages else ""
    approved = bool(answer)
    return {"validation": {"approved": approved, "issues": [] if approved else ["empty response"]}}


def route_after_validator(state: GenieState) -> str:
    v = state.get("validation") or {}
    turns = state.get("supervisor_turns", 0)
    if not v.get("approved", True) and turns < settings.SUPERVISOR_MAX_TURNS:
        return "supervisor"
    return END


__all__ = [
    "supervisor_node",
    "executor_node",
    "synthesiser_node",
    "validator_node",
    "route_after_validator",
]
