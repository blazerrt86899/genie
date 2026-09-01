"""Graph nodes (CLAUDE.md §9).

    START → prompt_enhancer → supervisor → executor → synthesiser → validator → {supervisor | END}

- prompt_enhancer: rewrites the latest message self-contained + an intent label.
- supervisor:  LLM planning via ``with_structured_output(SupervisorPlan)`` → a
               task ledger. Never hardcoded routing (CLAUDE.md §4.1).
- executor:    walks the ledger, runs each agent through the registry in
               dependency order, flips ``status`` and records results.
- synthesiser: composes the single user-facing reply (the only node whose tokens
               stream to the client).
- validator:   non-empty check + an LLM grounding check when agents ran; a reject
               feeds back to the supervisor for a capped re-plan.
"""

from __future__ import annotations

import time

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

from app.agents.events import emit as _emit
from app.agents.models import ainvoke, bump_tokens, get_chat_model, get_utility_model, tokens_of
from app.agents.registry import AGENT_REGISTRY, KNOWN_AGENTS, agent_menu
from app.agents.supervisor.prompts import (
    CHAT_SYSTEM_PROMPT,
    LEDGER_PREFACE,
    SUPERVISOR_SYSTEM_PROMPT,
    SYNTHESISER_SYSTEM_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)
from app.agents.supervisor.state import (
    GenieState,
    PlanStep,
    SupervisorPlan,
    TaskRecord,
    Validation,
)
from app.config import settings
from app.core.logging import preview

logger = structlog.get_logger(__name__)


# ─── shared helpers ──────────────────────────────────────────────────────────
# ``_emit`` is ``app.agents.events.emit`` (imported above).


_ATTACHMENT_CHAR_BUDGET = 24_000  # ~6k tokens total across all files in one turn


def _attachment_note(state: GenieState) -> str:
    """Short — filenames + rough size only. For the enhancer + supervisor so they
    know a file is in play (and can skip a web search) without paying for its body."""
    atts = state.get("attachments") or []
    if not atts:
        return ""
    rows = "\n".join(
        f"- {a['filename']} ({a['kind']}, ~{max(1, len(a['text']) // 5)} words)" for a in atts
    )
    return (
        "\n\nThe user attached these files with their message — their request is "
        f"probably about them (a web search is usually unnecessary):\n{rows}"
    )


def _format_attachments(state: GenieState) -> str:
    """The full extracted text, budgeted + visibly truncated. Synthesiser only."""
    atts = state.get("attachments") or []
    if not atts:
        return ""
    blocks: list[str] = []
    used = 0
    for a in atts:
        room = _ATTACHMENT_CHAR_BUDGET - used
        if room <= 0:
            blocks.append(f"### {a['filename']}\n…[skipped — attachment budget reached]")
            continue
        body = a["text"]
        if len(body) > room:
            body = body[:room] + f"\n…[truncated {len(a['text']) - room} chars]"
        used += len(body)
        blocks.append(f"### {a['filename']}\n{body}")
    return (
        "\n\n---\nAttached documents (the user included these with their message — "
        "answer from them):\n\n" + "\n\n".join(blocks)
    )


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
        if step.agent not in KNOWN_AGENTS:
            logger.warning("supervisor_plan_step_dropped", reason="unknown_agent", agent=step.agent)
            continue
        if key in seen:
            logger.debug("supervisor_plan_step_dropped", reason="duplicate", agent=step.agent)
            continue
        seen.add(key)
        kept.append((idx, step))
        if len(kept) >= _MAX_PLAN_STEPS:
            logger.warning("supervisor_plan_capped", cap=_MAX_PLAN_STEPS, proposed=len(steps))
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
    logger.info(
        "supervisor_start",
        turn=turns + 1,
        replan=turns > 0,
        tokens_used=usage.get("total", 0),
        available_agents=sorted(KNOWN_AGENTS),
    )
    if usage.get("total", 0) >= settings.MAX_TOKENS_PER_RUN:
        logger.warning(
            "token_budget_exhausted",
            total=usage.get("total"),
            limit=settings.MAX_TOKENS_PER_RUN,
        )
        return {"plan": [], "supervisor_turns": turns + 1, "intent": "token budget reached"}

    system = SUPERVISOR_SYSTEM_PROMPT.format(
        agent_menu=agent_menu(),
        ledger=_ledger_text(state.get("plan") or []) if turns else "",
    )
    if state.get("project_instructions"):
        system += f"\n\nProject instructions to respect:\n{state['project_instructions']}"
    system += _attachment_note(state)
    if state.get("enhanced_query"):
        system += (
            f"\n\nResolved request (from the prompt enhancer — use this as the "
            f"user's intent): {state['enhanced_query']}"
        )

    model = get_chat_model(
        model_id=state.get("model"), streaming=False, temperature=0
    ).with_structured_output(SupervisorPlan, include_raw=True)
    try:
        result = await ainvoke(model, [SystemMessage(content=system), *state["messages"]])
        plan_out: SupervisorPlan = result["parsed"]
    except Exception:  # noqa: BLE001
        logger.warning("supervisor_plan_failed", exc_info=True)
        return {
            "plan": [],
            "supervisor_turns": turns + 1,
            "intent": "planning failed — answering directly",
        }

    ledger = _plan_to_ledger(plan_out.steps)
    logger.info(
        "supervisor_planned",
        turn=turns + 1,
        rationale=preview(plan_out.rationale, 200),
        steps=[{"id": t["id"], "agent": t["agent"], "depends_on": t["depends_on"]} for t in ledger],
        direct_answer=not ledger,
    )
    return {
        "plan": ledger,
        "supervisor_turns": turns + 1,
        "token_usage": bump_tokens(usage, tokens_of(result), "supervisor"),
    }


async def executor_node(state: GenieState) -> dict:
    plan: list[TaskRecord] = [dict(t) for t in (state.get("plan") or [])]  # type: ignore[misc]
    results = dict(state.get("intermediate_results") or {})
    segments = list(state.get("streamed_segments") or [])
    if not plan:
        logger.info("executor_skip", reason="empty plan — synthesiser answers directly")
        return {
            "plan": plan,
            "intermediate_results": results,
            "streamed_segments": segments,
            "active_agents": [],
        }

    logger.info(
        "executor_start",
        tasks=[{"id": t["id"], "agent": t["agent"]} for t in plan],
    )

    # A live view so a later agent can read an earlier one's ledger + results.
    state = {**state, "plan": plan, "intermediate_results": results}
    await _emit("plan", {"steps": plan})

    done = {t["id"] for t in plan if t["status"] == "done"}
    segments_emitted = 0
    progressed = True
    while progressed:
        progressed = False
        for task in plan:
            if task["status"] != "pending" or not set(task["depends_on"]) <= done:
                continue
            progressed = True
            spec = AGENT_REGISTRY.get(task["agent"])
            task["status"] = "in_progress"
            started = time.perf_counter()
            logger.info(
                "agent_run_start",
                task_id=task["id"],
                agent=task["agent"],
                task=preview(task["description"], 120),
                depends_on=task["depends_on"],
            )
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
                logger.info(
                    "agent_run_done",
                    task_id=task["id"],
                    agent=task["agent"],
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                    summary_chars=len(res.summary or ""),
                    sources=len(res.sources or []),
                    streamed=res.stream,
                    summary_preview=preview(res.summary, 160),
                )
                if res.stream and res.summary.strip():
                    # user-ready now — its own message, shown before the rest runs
                    if segments_emitted:
                        await _emit("message_break", {})
                    await _emit("message_agents", {"agents": [task["agent"]]})
                    segments.append(res.summary.strip())
                    await _emit("segment", {"agent": task["agent"], "text": res.summary.strip()})
                    segments_emitted += 1
            except Exception as exc:  # noqa: BLE001
                task["status"] = "failed"
                task["error"] = str(exc)
                logger.warning(
                    "agent_run_failed",
                    task_id=task["id"],
                    agent=task["agent"],
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                    error=str(exc),
                    exc_info=True,
                )
            await _emit("agent_end", {"agent": task["agent"], "status": task["status"]})

    statuses = {t["id"]: t["status"] for t in plan}
    logger.info(
        "executor_done",
        statuses=statuses,
        segments=segments_emitted,
        results=sorted(results.keys()),
    )
    await _emit("plan", {"steps": plan})
    return {
        "plan": plan,
        "intermediate_results": results,
        "streamed_segments": segments,
        "active_agents": [],
    }


def _augment_system(system: str, state: GenieState) -> str:
    """Append project instructions + the full attachment text to a system prompt.
    Used by the synthesiser (the node that actually answers from the file)."""
    instructions = state.get("project_instructions")
    if instructions:
        system = f"{system}\n\n---\nProject instructions (follow these):\n{instructions}"
    return system + _format_attachments(state)


async def synthesiser_node(state: GenieState) -> dict:
    """Compose the request answer. Streamed segments (e.g. the greeting) have
    already been delivered to the user as their own message(s), so this node
    NEVER repeats them — it only produces the answer to the request."""
    plan = state.get("plan") or []
    results = state.get("intermediate_results") or {}
    segments = list(state.get("streamed_segments") or [])

    has_composable = any(
        results.get(t["id"]) and not results[t["id"]].get("streamed") for t in plan
    )

    # Nothing left to compose — the streamed segment(s) are the whole reply.
    if not has_composable:
        if segments:
            logger.info("synthesiser_relay_segment_only", segments=len(segments))
            text = "\n\n".join(segments)
            return {"messages": [AIMessage(content=text)], "final_response": text}
        # No agents ran → answer the user directly, in the current message.
        logger.info("synthesiser_direct_answer")
        await _emit("message_agents", {"agents": []})
        model = get_chat_model(model_id=state.get("model"), streaming=True)  # streaming → own retry
        resp = await model.ainvoke(
            [SystemMessage(content=_augment_system(CHAT_SYSTEM_PROMPT, state)), *state["messages"]]
        )
        return {
            "messages": [resp],
            "final_response": str(resp.content),
            "token_usage": bump_tokens(
                state.get("token_usage"), tokens_of(resp), "synthesiser"
            ),
        }

    # This composed answer is its own message. If a segment (greeting) was already
    # sent, break onto a new one; otherwise it fills the current (first) message.
    composed_agents = list(
        dict.fromkeys(
            r["agent"] for t in plan if (r := results.get(t["id"])) and not r.get("streamed")
        )
    )
    logger.info(
        "synthesiser_compose",
        from_agents=composed_agents,
        after_greeting=bool(segments),
        finding_chars=sum(len(r.get("summary") or "") for r in results.values()),
    )
    if segments:
        await _emit("message_break", {})
    await _emit("message_agents", {"agents": composed_agents})

    system = _augment_system(SYNTHESISER_SYSTEM_PROMPT, state)
    findings = _format_findings(plan, results)
    if segments:
        findings += (
            "\n\n(You have already sent the user a separate greeting message. Do "
            "NOT greet again — reply straight to their request.)"
        )

    convo = [*state["messages"], SystemMessage(content="Specialist findings:\n" + findings)]
    model = get_chat_model(model_id=state.get("model"), streaming=True)  # streaming → own retry
    resp = await model.ainvoke([SystemMessage(content=system), *convo])
    logger.info("synthesiser_done", answer_chars=len(str(resp.content)))
    return {
        "messages": [resp],
        "final_response": str(resp.content),
        "token_usage": bump_tokens(state.get("token_usage"), tokens_of(resp), "synthesiser"),
    }


async def validator_node(state: GenieState) -> dict:
    """Non-empty check, then — only when agents produced findings — an LLM
    grounding / sanity check. A reject routes back to the supervisor (capped)."""
    messages = state.get("messages") or []
    answer = str(messages[-1].content).strip() if messages else ""
    if not answer:
        logger.info("validator_verdict", approved=False, reason="empty")
        return {"validation": {"approved": False, "issues": ["empty response"]}}

    results = state.get("intermediate_results") or {}
    plan = state.get("plan") or []
    composable = {
        k: r for k, r in results.items() if not r.get("streamed")
    }
    # Pure model answers (no agents) have nothing external to ground-check.
    if not composable or not settings.llm_configured:
        logger.info("validator_verdict", approved=True, checked="non_empty_only")
        return {"validation": {"approved": True, "issues": []}}

    findings = _format_findings(plan, results)
    try:
        model = get_utility_model(temperature=0).with_structured_output(
            Validation, include_raw=True
        )
        result = await ainvoke(
            model,
            [
                SystemMessage(content=VALIDATOR_SYSTEM_PROMPT),
                HumanMessage(
                    content=(
                        f"Draft reply:\n{answer}\n\nAgent findings:\n{findings}\n\n"
                        "Approve unless the reply is off-topic, a refusal/error, or "
                        "contradicts the findings."
                    )
                ),
            ],
        )
        verdict: Validation = result["parsed"]
    except Exception:  # noqa: BLE001 — don't block a good answer on a validator error
        logger.warning("validator_check_failed", exc_info=True)
        return {"validation": {"approved": True, "issues": []}}

    logger.info(
        "validator_verdict",
        approved=verdict.approved,
        issues=verdict.issues,
        checked="grounding",
    )
    return {
        "validation": {"approved": verdict.approved, "issues": verdict.issues},
        "token_usage": bump_tokens(state.get("token_usage"), tokens_of(result), "validator"),
    }


def route_after_validator(state: GenieState) -> str:
    v = state.get("validation") or {}
    turns = state.get("supervisor_turns", 0)
    if not v.get("approved", True) and turns < settings.SUPERVISOR_MAX_TURNS:
        logger.warning(
            "validator_replan",
            turn=turns,
            max_turns=settings.SUPERVISOR_MAX_TURNS,
            issues=v.get("issues"),
        )
        return "supervisor"
    logger.debug("graph_end", turns=turns, approved=v.get("approved", True))
    return END


__all__ = [
    "supervisor_node",
    "executor_node",
    "synthesiser_node",
    "validator_node",
    "route_after_validator",
]
