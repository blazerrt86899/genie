"""Web Search agent (CLAUDE.md §12)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.agents.web_search import agent as ws
from app.agents.web_search.agent import run_web_search
from langchain_core.messages import HumanMessage

_TAVILY = {
    "answer": "Artemis II is targeted for 2025.",
    "results": [
        {
            "title": "NASA Artemis",
            "url": "https://nasa.gov/artemis",
            "content": "Artemis II will fly around the Moon.",
        },
        {
            "title": "Wiki",
            "url": "https://en.wikipedia.org/wiki/Artemis_2",
            "content": "Crewed lunar flyby.",
        },
    ],
}


def _settings(*, tavily_configured=True, llm_configured=True):
    return SimpleNamespace(tavily_configured=tavily_configured, llm_configured=llm_configured)


def _state():
    return {"messages": [HumanMessage(content="latest on Artemis")]}


def _task(desc="latest news on the Artemis program"):
    return {"id": "t1", "description": desc, "agent": "web_search"}


async def test_raises_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(ws, "settings", _settings(tavily_configured=False))
    with pytest.raises(RuntimeError):
        await run_web_search(_state(), _task())


async def test_summarises_results_with_sources(monkeypatch) -> None:
    monkeypatch.setattr(ws, "settings", _settings())

    async def fake_search(query, **_):
        assert "Artemis" in query
        return _TAVILY

    class FakeModel:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="Artemis II will do a crewed lunar flyby [1].")

    monkeypatch.setattr(ws, "tavily_search", fake_search)
    monkeypatch.setattr(ws, "get_chat_model", lambda **_: FakeModel())

    res = await run_web_search(_state(), _task())
    assert "[1]" in res.summary
    assert {s["url"] for s in res.sources} == {
        "https://nasa.gov/artemis",
        "https://en.wikipedia.org/wiki/Artemis_2",
    }


async def test_without_llm_returns_tavily_answer(monkeypatch) -> None:
    monkeypatch.setattr(ws, "settings", _settings(llm_configured=False))

    async def fake_search(_query, **_):
        return _TAVILY

    monkeypatch.setattr(ws, "tavily_search", fake_search)
    res = await run_web_search(_state(), _task())
    assert "Artemis II is targeted for 2025." in res.summary
