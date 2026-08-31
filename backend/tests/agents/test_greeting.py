"""Greeting agent (CLAUDE.md §12)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.agents.greeting import agent as greeting_agent
from app.agents.greeting.agent import part_of_day, run_greeting
from app.agents.greeting.prompts import TEMPLATE_GREETINGS
from langchain_core.messages import HumanMessage


@pytest.mark.parametrize(
    ("hour", "bucket"),
    [(6, "morning"), (11, "morning"), (12, "afternoon"), (16, "afternoon"),
     (17, "evening"), (21, "evening"), (22, "night"), (3, "night")],
)
def test_part_of_day(hour: int, bucket: str) -> None:
    assert part_of_day(hour) == bucket


def _state(hour):
    return {"messages": [HumanMessage(content="hi there")], "client_hour": hour}


def _task():
    return {"id": "t1", "description": "greet", "agent": "greeting"}


async def test_falls_back_to_template_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(greeting_agent, "settings", SimpleNamespace(llm_configured=False))
    res = await run_greeting(_state(23), _task())
    assert res.summary == TEMPLATE_GREETINGS["night"]


async def test_uses_llm_and_time_bucket(monkeypatch) -> None:
    monkeypatch.setattr(greeting_agent, "settings", SimpleNamespace(llm_configured=True))
    seen: dict = {}

    class FakeModel:
        async def ainvoke(self, messages):
            seen["system"] = messages[0].content
            return SimpleNamespace(content="Good evening, friend! 🌆")

    monkeypatch.setattr(greeting_agent, "get_utility_model", lambda **_: FakeModel())
    res = await run_greeting(_state(18), _task())
    assert res.summary == "Good evening, friend! 🌆"
    assert "evening" in seen["system"]


async def test_llm_error_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(greeting_agent, "settings", SimpleNamespace(llm_configured=True))

    class Boom:
        async def ainvoke(self, _messages):
            raise RuntimeError("api down")

    monkeypatch.setattr(greeting_agent, "get_utility_model", lambda **_: Boom())
    res = await run_greeting(_state(9), _task())
    assert res.summary == TEMPLATE_GREETINGS["morning"]
