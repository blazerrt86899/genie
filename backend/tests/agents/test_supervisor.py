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
    synthesiser_node,
    validator_node,
)
from app.agents.supervisor.state import PlanStep, SupervisorPlan, Validation
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

# ─── plan validation ─────────────────────────────────────────────────────────


def test_plan_drops_unknown_and_exact_dupes_and_remaps_deps() -> None:
    steps = [
        PlanStep(description="greet", agent="greeting"),
        PlanStep(description="ignored", agent="bogus"),
        PlanStep(description="greet", agent="greeting"),  # exact dupe → dropped
        PlanStep(description="search", agent="web_search", depends_on=[1]),
    ]
    ledger = _plan_to_ledger(steps)
    assert [t["agent"] for t in ledger] == ["greeting", "web_search"]
    assert ledger[0]["id"] == "t1"
    assert ledger[1]["depends_on"] == ["t1"]
    assert all(t["status"] == "pending" for t in ledger)


def test_plan_allows_one_agent_across_distinct_tasks() -> None:
    steps = [
        PlanStep(description="weather in Mussoorie", agent="web_search"),
        PlanStep(description="latest Artemis news", agent="web_search"),
    ]
    ledger = _plan_to_ledger(steps)
    assert [t["agent"] for t in ledger] == ["web_search", "web_search"]
    assert [t["id"] for t in ledger] == ["t1", "t2"]


def test_plan_is_capped() -> None:
    steps = [PlanStep(description=f"q{i}", agent="web_search") for i in range(20)]
    assert len(_plan_to_ledger(steps)) == 6


# ─── supervisor node ─────────────────────────────────────────────────────────


def _fake_model(returns=None, raises=None):
    """A stand-in for get_chat_model(...).with_structured_output(X, include_raw=True)."""

    class _Inner:
        async def ainvoke(self, _messages, **_kw):
            if raises:
                raise raises
            return {"parsed": returns, "raw": SimpleNamespace(usage_metadata={"total_tokens": 11})}

    return SimpleNamespace(with_structured_output=lambda _m, **_kw: _Inner())


async def test_supervisor_node_builds_ledger(monkeypatch) -> None:
    plan = SupervisorPlan(
        steps=[PlanStep(description="find news", agent="web_search")],
        rationale="needs current info",
    )
    monkeypatch.setattr(nodes, "get_chat_model", lambda **_: _fake_model(returns=plan))
    out = await supervisor_node(
        {
            "messages": [HumanMessage(content="what's new in AI?")],
            "supervisor_turns": 0,
            "token_usage": {"total": 0, "by_agent": {}},
        }
    )
    assert [t["agent"] for t in out["plan"]] == ["web_search"]
    assert out["supervisor_turns"] == 1
    assert out["token_usage"]["total"] == 11  # tokens tracked for the budget guard


async def test_supervisor_node_survives_llm_error(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes, "get_chat_model", lambda **_: _fake_model(raises=RuntimeError("no key"))
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
        assert state["intermediate_results"]["t1"]["summary"] == "A done"
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
    assert out["intermediate_results"]["t2"]["sources"][0]["url"] == "http://x"
    assert out["intermediate_results"]["t2"]["agent"] == "b"
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


async def test_executor_streams_a_segment_for_stream_results(monkeypatch) -> None:
    emitted: list[tuple[str, dict]] = []

    async def run_hi(_state, _task):
        return AgentResult(summary="Good evening!", stream=True)

    async def run_search(_state, _task):
        return AgentResult(summary="It is 22°C.")

    async def fake_emit(name, data):
        emitted.append((name, data))

    monkeypatch.setattr(
        nodes,
        "AGENT_REGISTRY",
        {
            "greeting": registry.AgentSpec("greeting", "", run_hi),
            "web_search": registry.AgentSpec("web_search", "", run_search),
        },
    )
    monkeypatch.setattr(nodes, "_emit", fake_emit)

    state = {
        "plan": [
            {"id": "t1", "description": "greet", "agent": "greeting", "status": "pending",
             "depends_on": [], "result": None, "error": None},
            {"id": "t2", "description": "weather", "agent": "web_search", "status": "pending",
             "depends_on": [], "result": None, "error": None},
        ],
        "intermediate_results": {},
        "messages": [],
    }
    out = await executor_node(state)
    assert out["streamed_segments"] == ["Good evening!"]
    names = [n for n, _ in emitted]
    # the greeting message is announced right before its content
    assert ("message_agents", {"agents": ["greeting"]}) in emitted
    assert names.index("message_agents") < names.index("segment")
    assert ("segment", {"agent": "greeting", "text": "Good evening!"}) in emitted
    assert out["intermediate_results"]["t1"]["streamed"] is True
    assert out["intermediate_results"]["t2"]["streamed"] is False


async def test_synthesiser_composes_only_the_request_not_the_greeting(monkeypatch) -> None:
    seen: dict = {}

    class FakeModel:
        async def ainvoke(self, messages):
            seen["prompt"] = "\n".join(str(m.content) for m in messages)
            return SimpleNamespace(content="It is 22°C in Mussoorie [1].")

    emitted: list[tuple[str, dict]] = []

    async def fake_emit(name, data):
        emitted.append((name, data))

    monkeypatch.setattr(nodes, "get_chat_model", lambda **_: FakeModel())
    monkeypatch.setattr(nodes, "_emit", fake_emit)

    state = {
        "messages": [HumanMessage(content="hi, weather in Mussoorie?")],
        "streamed_segments": ["Good evening!"],
        "plan": [
            {"id": "t1", "agent": "greeting", "description": "greet", "status": "done",
             "depends_on": [], "result": "Good evening!", "error": None},
            {"id": "t2", "agent": "web_search", "description": "weather", "status": "done",
             "depends_on": [], "result": "22C", "error": None},
        ],
        "intermediate_results": {
            "t1": {"agent": "greeting", "summary": "Good evening!", "streamed": True,
                   "sources": [], "detail": None},
            "t2": {"agent": "web_search", "summary": "22C", "streamed": False,
                   "sources": [{"title": "wx", "url": "http://wx"}], "detail": None},
        },
    }
    out = await synthesiser_node(state)
    # greeting is delivered as its own message — the synthesiser must NOT repeat it
    assert out["final_response"] == "It is 22°C in Mussoorie [1]."
    assert "greet again" in seen["prompt"].lower()
    # it breaks onto a new message and tags it with the composing agent
    assert ("message_break", {}) in emitted
    assert ("message_agents", {"agents": ["web_search"]}) in emitted


# ─── validator + routing ─────────────────────────────────────────────────────


async def test_validator_approves_non_empty_rejects_empty() -> None:
    # no agent findings → non-empty check only, no LLM call
    ok = await validator_node({"messages": [AIMessage(content="here you go")]})
    assert ok["validation"]["approved"] is True

    bad = await validator_node({"messages": [AIMessage(content="   ")]})
    assert bad["validation"]["approved"] is False
    assert bad["validation"]["issues"]


async def test_validator_runs_grounding_check_when_agents_ran(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes, "settings", SimpleNamespace(llm_configured=True, SUPERVISOR_MAX_TURNS=2)
    )
    monkeypatch.setattr(
        nodes,
        "get_utility_model",
        lambda **_: _fake_model(
            returns=Validation(approved=False, issues=["contradicts sources"])
        ),
    )
    state = {
        "messages": [AIMessage(content="The Eiffel Tower is in Berlin.")],
        "plan": [
            {"id": "t1", "agent": "web_search", "description": "loc", "status": "done",
             "depends_on": [], "result": "Paris", "error": None},
        ],
        "intermediate_results": {
            "t1": {"agent": "web_search", "summary": "The Eiffel Tower is in Paris.",
                   "streamed": False, "sources": [], "detail": None},
        },
    }
    out = await validator_node(state)
    assert out["validation"]["approved"] is False
    assert "contradicts sources" in out["validation"]["issues"]


async def test_retriever_node_gated(monkeypatch) -> None:
    # no KB → no-op
    assert await nodes.retriever_node({"has_kb": False, "needs_documents": True}) == {}
    # KB but the enhancer said no → no-op
    assert await nodes.retriever_node({"has_kb": True, "needs_documents": False}) == {}

    calls = {}

    async def _retrieve(db, pid, uid, query, s):
        calls["query"] = query
        return [{"content": "chunk", "similarity": 0.9, "heading": None, "filename": "f.md"}]

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("app.services.rag.retrieval_service.retrieve", _retrieve)
    monkeypatch.setattr(nodes, "_emit", _noop)

    class _CM:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.db.session.get_sessionmaker", lambda: (lambda: _CM()))
    monkeypatch.setattr(nodes, "settings", SimpleNamespace(llm_configured=True))

    import uuid

    out = await nodes.retriever_node(
        {
            "has_kb": True,
            "needs_documents": True,
            "enhanced_query": "what does the doc say",
            "user_id": str(uuid.uuid4()),
            "rag_settings": {},
            "metadata": {"project_id": str(uuid.uuid4())},
        }
    )
    assert calls["query"] == "what does the doc say"
    assert out["retrieved_chunks"][0]["content"] == "chunk"


def test_kb_helpers() -> None:
    assert nodes._kb_note({}) == ""
    assert nodes._format_kb({}) == ""

    gate = {"has_kb": True, "needs_documents": True}
    st = {
        **gate,
        "retrieved_chunks": [{"content": "body text", "filename": "spec.md", "heading": "Intro"}],
    }
    note = nodes._kb_note(st)
    assert "spec.md" in note and "web_search" in note  # tells the supervisor not to web_search
    full = nodes._format_kb(st)
    assert "spec.md — Intro" in full and "body text" in full

    # KB engaged but found nothing → different note, still not empty
    miss = nodes._kb_note({**gate, "retrieved_chunks": []})
    assert "nothing relevant was found" in miss


def test_synthesiser_prompt_carries_format_guide() -> None:
    from app.agents.supervisor.prompts import (
        CHAT_SYSTEM_PROMPT,
        RESPONSE_FORMAT_GUIDE,
        SYNTHESISER_SYSTEM_PROMPT,
    )

    # the drafter spec is baked into every user-facing prompt
    assert RESPONSE_FORMAT_GUIDE in SYNTHESISER_SYSTEM_PROMPT
    assert RESPONSE_FORMAT_GUIDE in CHAT_SYSTEM_PROMPT
    for token in ("```sql", "GFM pipe tables", "Fenced code blocks"):
        assert token in RESPONSE_FORMAT_GUIDE
    # the business-document card spec rides along on both prompts
    for token in ("```document", "kind:", "cover letter", "memo"):
        assert token in SYNTHESISER_SYSTEM_PROMPT and token in CHAT_SYSTEM_PROMPT
    # …and survives _augment_system (project instructions / attachments / KB)
    state = {"project_instructions": "be terse"}
    composed = nodes._augment_system(SYNTHESISER_SYSTEM_PROMPT, state)
    assert RESPONSE_FORMAT_GUIDE in composed and "be terse" in composed
    # the old contradictory "Sources heading" instruction is gone
    assert "Sources" not in SYNTHESISER_SYSTEM_PROMPT.split(RESPONSE_FORMAT_GUIDE)[0]


def test_attachment_helpers() -> None:
    assert nodes._attachment_note({}) == ""
    assert nodes._format_attachments({}) == ""

    small = {"attachments": [{"filename": "a.md", "kind": "md", "text": "short body"}]}
    note = nodes._attachment_note(small)
    assert "a.md" in note and "md" in note
    full = nodes._format_attachments(small)
    assert "### a.md" in full and "short body" in full
    assert "truncated" not in full

    big = {"attachments": [{"filename": "big.txt", "kind": "txt", "text": "x" * 30_000}]}
    full = nodes._format_attachments(big)
    assert "…[truncated" in full
    assert len(full) < 30_000 + 500  # capped near the budget, not the full 30k


async def test_cache_lookup_node_gates(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes, "settings", SimpleNamespace(RESPONSE_CACHE_ENABLED=True, llm_configured=True)
    )
    base = {
        "messages": [HumanMessage(content="explain how a bloom filter works internally")],
        "user_id": "u1",
        "enhanced_query": "explain how a bloom filter works internally",
        "has_kb": False,
        "needs_documents": False,
        "metadata": {},
    }
    # turn 2 → skip
    assert await nodes.cache_lookup_node({**base, "messages": base["messages"] * 2}) == {}
    # KB project → skip
    assert await nodes.cache_lookup_node({**base, "has_kb": True}) == {}
    # time-sensitive query → skip
    assert await nodes.cache_lookup_node(
        {**base, "enhanced_query": "what's the latest news today"}
    ) == {}


async def test_cache_lookup_node_hit(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes, "settings", SimpleNamespace(RESPONSE_CACHE_ENABLED=True, llm_configured=True)
    )
    import app.services.cache_service as cs

    async def _hit(_db, _uid, _q):
        return {"response": "a cached explanation", "similarity": 0.95, "age_s": 60.0}

    monkeypatch.setattr(cs, "lookup", _hit)

    class _SM:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self):
                    return None

                async def __aexit__(self, *_a):
                    return False

            return _Ctx()

    monkeypatch.setattr("app.db.session.get_sessionmaker", lambda: _SM())

    out = await nodes.cache_lookup_node({
        "messages": [HumanMessage(content="explain how a bloom filter works internally")],
        "user_id": "u1",
        "enhanced_query": "explain how a bloom filter works internally",
        "has_kb": False, "needs_documents": False, "metadata": {},
    })
    assert out["final_response"] == "a cached explanation"
    assert out["metadata"]["cache_hit"]["similarity"] == 0.95
    assert nodes.route_after_cache(out) == END
    assert nodes.route_after_cache({"metadata": {}}) == "retriever"


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
