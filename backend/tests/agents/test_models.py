"""LLM retry + token helpers (CLAUDE.md §4)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from app.agents import models
from app.agents.models import ainvoke, bump_tokens, tokens_of
from tenacity import wait_fixed


class _Transient(Exception):
    """Stand-in for a retryable OpenAI error."""


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch):
    monkeypatch.setattr(models, "_retry_wait", wait_fixed(0))
    monkeypatch.setattr(models, "_TRANSIENT", (_Transient,))


def test_bump_tokens_accumulates():
    u = bump_tokens(None, 10, "supervisor")
    assert u == {"total": 10, "by_agent": {"supervisor": 10}}
    u = bump_tokens(u, 5, "synthesiser")
    assert u["total"] == 15
    assert u["by_agent"] == {"supervisor": 10, "synthesiser": 5}


def test_tokens_of_handles_both_shapes():
    msg = SimpleNamespace(usage_metadata={"total_tokens": 42})
    assert tokens_of(msg) == 42
    assert tokens_of({"raw": msg, "parsed": object()}) == 42
    assert tokens_of(SimpleNamespace(usage_metadata=None)) == 0


async def test_ainvoke_retries_transient_then_succeeds():
    calls = {"n": 0}

    class Flaky:
        async def ainvoke(self, _messages, **_kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise _Transient("try again")
            return SimpleNamespace(content="ok")

    out = await ainvoke(Flaky(), [])
    assert out.content == "ok"
    assert calls["n"] == 3


async def test_ainvoke_gives_up_after_max_attempts():
    calls = {"n": 0}

    class Dead:
        async def ainvoke(self, _messages, **_kw):
            calls["n"] += 1
            raise _Transient("always down")

    with pytest.raises(_Transient):
        await ainvoke(Dead(), [])
    assert calls["n"] == models._RETRY_ATTEMPTS


async def test_ainvoke_does_not_retry_non_transient():
    calls = {"n": 0}

    class Bad:
        async def ainvoke(self, _messages, **_kw):
            calls["n"] += 1
            raise ValueError("bad schema")

    with pytest.raises(ValueError):
        await ainvoke(Bad(), [])
    assert calls["n"] == 1
