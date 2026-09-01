"""Prompt Enhancer node (CLAUDE.md §12)."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.prompt_enhancer import agent as pe
from app.agents.prompt_enhancer.agent import prompt_enhancer_node
from app.agents.supervisor.state import EnhancedPrompt
from langchain_core.messages import AIMessage, HumanMessage


def _state(*contents):
    msgs = []
    for i, c in enumerate(contents):
        msgs.append(HumanMessage(content=c) if i % 2 == 0 else AIMessage(content=c))
    return {"messages": msgs, "token_usage": {"total": 0, "by_agent": {}}}


async def test_rewrites_and_tracks_tokens(monkeypatch):
    monkeypatch.setattr(pe, "settings", SimpleNamespace(llm_configured=True))

    class _Inner:
        async def ainvoke(self, _messages, **_kw):
            return {
                "parsed": EnhancedPrompt(
                    intent="weather lookup", enhanced_query="today's weather in Mussoorie"
                ),
                "raw": SimpleNamespace(usage_metadata={"total_tokens": 9}),
            }

    monkeypatch.setattr(pe, "emit", _noop)
    monkeypatch.setattr(
        pe,
        "get_utility_model",
        lambda **_: SimpleNamespace(with_structured_output=lambda _m, **_k: _Inner()),
    )

    out = await prompt_enhancer_node(_state("Mussoorie?", "which city?", "the weather there"))
    assert out["intent"] == "weather lookup"
    assert out["enhanced_query"] == "today's weather in Mussoorie"
    assert out["token_usage"]["total"] == 9


async def test_passthrough_without_llm(monkeypatch):
    monkeypatch.setattr(pe, "settings", SimpleNamespace(llm_configured=False))
    out = await prompt_enhancer_node(_state("hello there"))
    assert out == {"intent": "unknown", "enhanced_query": "hello there"}


async def test_survives_llm_error(monkeypatch):
    monkeypatch.setattr(pe, "settings", SimpleNamespace(llm_configured=True))
    monkeypatch.setattr(pe, "emit", _noop)

    class _Boom:
        async def ainvoke(self, _messages, **_kw):
            raise RuntimeError("bad json")

    monkeypatch.setattr(
        pe,
        "get_utility_model",
        lambda **_: SimpleNamespace(with_structured_output=lambda _m, **_k: _Boom()),
    )
    out = await prompt_enhancer_node(_state("do the thing"))
    assert out["enhanced_query"] == "do the thing"
    assert out["intent"] == "unknown"


async def _noop(*_a, **_k):
    return None
