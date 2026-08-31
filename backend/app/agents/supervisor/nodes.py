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


_MAX_PLAN_STEPS = 6


def _plan_to_ledger(steps: list[PlanStep]) -> list[TaskRecord]:
    """Validate the LLM's plan → an executable ledger.

    Drops steps for unknown agents and exact (agent, description) repeats; an
    agent MAY appear more than once for genuinely distinct sub-tasks. Caps the
    plan at ``_MAX_PLAN_STEPS`` and remaps 1-based ``depends_on`` → task ids.
    """
    kept: list[tuple[int, PlanStep]] = []
    seen: set[tuple[str, str]] = set()
    for idx, step in enumerate(steps, start=1):
        key = (step.agent, step.description.strip().lower())
        if step.agent not in KNOWN_AGENTS or key in seen:
            continue
        seen.add(key)
        kept.append((idx, step))
        if len(kept) >= _MAX_PLAN_STEPS:
            break

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


def _format_findings(plan: list[TaskRecord], results: dict) -> str:
    """Render non-streamed findings in plan order, with globally-numbered sources."""
    blocks: list[str] = []
    src_no = 0
    for task in plan:
        r = results.get(task["id"])
        if not r or r.get("streamed"):
            continue
        block = f"## Step: {task['description']} (agent: {r.get('agent', task['agent'])})\n"
        block += r.get("summary", "") or ""
        sources = r.get("sources") or []
        if sources:
            lines = []
            for s in sources:
                src_no += 1
                lines.append(f"[{src_no}] {s.get('title', '')} — {s.get('url', '')}")
            block += "\n\nSources:\n" + "\n".join(lines)
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
    segments = list(state.get("streamed_segments") or [])
    if not plan:
        return {
            "plan": plan,
            "intermediate_results": results,
            "streamed_segments": segments,
            "active_agents": [],
        }

    # A live view so a later agent can read an earlier one's ledger + results.
    state = {**state, "plan": plan, "intermediate_results": results}
    await _emit("plan", {"steps": plan})
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
                results[task["id"]] = {
                    "agent": task["agent"],
                    "summary": res.summary,
                    "detail": res.detail,
                    "sources": res.sources,
                    "streamed": bool(res.stream),
                }
                done.add(task["id"])
                if res.stream and res.summary.strip():
                    # user-ready now — show it before the remaining steps run
                    segments.append(res.summary.strip())
                    await _emit("segment", {"agent": task["agent"], "text": res.summary.strip()})
            except Exception as exc:  # noqa: BLE001
                task["status"] = "failed"
                task["error"] = str(exc)
                logger.warning("agent_failed", agent=task["agent"], error=str(exc))
            await _emit("agent_end", {"agent": task["agent"], "status": task["status"]})

    await _emit("plan", {"steps": plan})
    return {
        "plan": plan,
        "intermediate_results": results,
        "streamed_segments": segments,
        "active_agents": [],
    }


def _with_project(system: str, state: GenieState) -> str:
    instructions = state.get("project_instructions")
    if instructions:
        return f"{system}\n\n---\nProject instructions (follow these):\n{instructions}"
    return system


async def synthesiser_node(state: GenieState) -> dict:
    plan = state.get("plan") or []
    results = state.get("intermediate_results") or {}
    segments = list(state.get("streamed_segments") or [])
    prefix = "\n\n".join(segments)

    has_composable = any(
        results.get(t["id"]) and not results[t["id"]].get("streamed") for t in plan
    )

    # Nothing left for the LLM to compose.
    if not has_composable:
        if prefix:  # e.g. a lone greeting — already shown, just finalise it
            return {"messages": [AIMessage(content=prefix)], "final_response": prefix}
        # No agents ran → answer the user directly.
        model = get_chat_model(streaming=True)
        resp = await model.ainvoke(
            [SystemMessage(content=_with_project(CHAT_SYSTEM_PROMPT, state)), *state["messages"]]
        )
        return {"messages": [resp], "final_response": str(resp.content)}

    system = _with_project(SYNTHESISER_SYSTEM_PROMPT, state)
    findings = _format_findings(plan, results)
    if prefix:
        findings = (
            f"The user has ALREADY been shown this (do not repeat it, do not greet "
            f"again):\n{prefix}\n\n---\n{findings}"
        )

    convo = [*state["messages"], SystemMessage(content="Specialist findings:\n" + findings)]
    model = get_chat_model(streaming=True)
    resp = await model.ainvoke([SystemMessage(content=system), *convo])

    body = str(resp.content)
    full = f"{prefix}\n\n{body}" if prefix else body
    return {"messages": [AIMessage(content=full)], "final_response": full}


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
