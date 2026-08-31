"""Supervisor / executor / validator (CLAUDE.md §9, §16)."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents import registry
from app.agents.base import AgentResult
from app.agents.supervisor import nodes
from app.agents.supervisor.nodes import (
    _plan_to_ledger,
    executor_node,
    route_after_validator,
    supervisor_node,
    validator_node,
)
from app.agents.supervisor.state import PlanStep, SupervisorPlan
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

# ─── plan validation ─────────────────────────────────────────────────────────


def test_plan_drops_unknown_and_duplicate_agents_and_remaps_deps() -> None:
    steps = [
        PlanStep(description="greet", agent="greeting"),
        PlanStep(description="ignored", agent="bogus"),
        PlanStep(description="dup", agent="greeting"),
        PlanStep(description="search", agent="web_search", depends_on=[1]),
    ]
    ledger = _plan_to_ledger(steps)
    assert [t["agent"] for t in ledger] == ["greeting", "web_search"]
    assert ledger[0]["id"] == "t1"
    assert ledger[1]["depends_on"] == ["t1"]
    assert all(t["status"] == "pending" for t in ledger)


# ─── supervisor node ─────────────────────────────────────────────────────────


async def test_supervisor_node_builds_ledger(monkeypatch) -> None:
    plan = SupervisorPlan(
        steps=[PlanStep(description="find news", agent="web_search")],
        rationale="needs current info",
    )

    class FakeStructured:
        async def ainvoke(self, _messages):
            return plan

    monkeypatch.setattr(
        nodes,
        "get_chat_model",
        lambda **_: SimpleNamespace(with_structured_output=lambda _m: FakeStructured()),
    )
    out = await supervisor_node(
        {"messages": [HumanMessage(content="what's new in AI?")], "supervisor_turns": 0}
    )
    assert [t["agent"] for t in out["plan"]] == ["web_search"]
    assert out["supervisor_turns"] == 1
    assert out["intent"] == "needs current info"


async def test_supervisor_node_survives_llm_error(monkeypatch) -> None:
    class Boom:
        async def ainvoke(self, _messages):
            raise RuntimeError("no key")

    monkeypatch.setattr(
        nodes,
        "get_chat_model",
        lambda **_: SimpleNamespace(with_structured_output=lambda _m: Boom()),
    )
    out = await supervisor_node({"messages": [HumanMessage(content="hi")], "supervisor_turns": 0})
    assert out["plan"] == []
    assert out["supervisor_turns"] == 1


# ─── executor node ───────────────────────────────────────────────────────────


async def test_executor_runs_agents_in_dependency_order(monkeypatch) -> None:
    calls: list[str] = []
    events: list[tuple[str, str]] = []

    async def run_a(_state, _task):
        calls.append("a")
        return AgentResult(summary="A done")

    async def run_b(state, _task):
        calls.append("b")
        assert state["intermediate_results"]["a"]["summary"] == "A done"
        return AgentResult(summary="B done", sources=[{"title": "x", "url": "http://x"}])

    monkeypatch.setattr(
        nodes,
        "AGENT_REGISTRY",
        {
            "a": registry.AgentSpec("a", "", run_a),
            "b": registry.AgentSpec("b", "", run_b),
        },
    )

    async def fake_emit(name, data):
        if name in ("agent_start", "agent_end"):
            events.append((name, data["agent"]))

    monkeypatch.setattr(nodes, "_emit", fake_emit)

    state = {
        "plan": [
            {"id": "t1", "description": "do a", "agent": "a", "status": "pending",
             "depends_on": [], "result": None, "error": None},
            {"id": "t2", "description": "do b", "agent": "b", "status": "pending",
             "depends_on": ["t1"], "result": None, "error": None},
        ],
        "intermediate_results": {},
        "messages": [],
    }
    out = await executor_node(state)
    assert calls == ["a", "b"]
    assert [t["status"] for t in out["plan"]] == ["done", "done"]
    assert out["plan"][0]["result"] == "A done"
    assert out["intermediate_results"]["b"]["sources"][0]["url"] == "http://x"
    assert ("agent_start", "a") in events and ("agent_end", "b") in events


async def test_executor_marks_failed_agent(monkeypatch) -> None:
    async def boom(_state, _task):
        raise RuntimeError("kaboom")

    async def fake_emit(*_a, **_k):
        return None

    monkeypatch.setattr(nodes, "AGENT_REGISTRY", {"x": registry.AgentSpec("x", "", boom)})
    monkeypatch.setattr(nodes, "_emit", fake_emit)

    state = {
        "plan": [{"id": "t1", "description": "x", "agent": "x", "status": "pending",
                  "depends_on": [], "result": None, "error": None}],
        "intermediate_results": {},
        "messages": [],
    }
    out = await executor_node(state)
    assert out["plan"][0]["status"] == "failed"
    assert "kaboom" in out["plan"][0]["error"]


# ─── validator + routing ─────────────────────────────────────────────────────


async def test_validator_approves_non_empty_rejects_empty() -> None:
    ok = await validator_node({"messages": [AIMessage(content="here you go")]})
    assert ok["validation"]["approved"] is True

    bad = await validator_node({"messages": [AIMessage(content="   ")]})
    assert bad["validation"]["approved"] is False
    assert bad["validation"]["issues"]


def test_route_after_validator() -> None:
    assert route_after_validator({"validation": {"approved": True}, "supervisor_turns": 1}) == END
    assert (
        route_after_validator({"validation": {"approved": False}, "supervisor_turns": 1})
        == "supervisor"
    )
    # cap reached → stop looping
    assert (
        route_after_validator({"validation": {"approved": False}, "supervisor_turns": 9}) == END
    )
