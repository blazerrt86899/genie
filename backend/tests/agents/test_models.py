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


# ─── Model catalog / resolver ────────────────────────────────────────────────


@pytest.fixture
def _all_providers(monkeypatch):
    """Pretend every provider has a key."""
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-x")


def test_available_models_filters_by_key(monkeypatch, _all_providers):
    from app.config import settings

    ids = {m.id for m in models.available_models()}
    assert {"gpt-4o", "claude-sonnet", "groq-oss-120b"} <= ids

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    ids = {m.id for m in models.available_models()}
    assert not any(i.startswith("claude") for i in ids)
    assert "gpt-4o" in ids


def test_resolve_model_spec_known_unknown_and_keyless(monkeypatch, _all_providers):
    from app.config import settings

    assert models.resolve_model_spec("claude-sonnet").model == "claude-sonnet-5"

    # unknown id → the server default
    assert models.resolve_model_spec("nope").id == "_default"

    # known id but its provider lost its key → the server default
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    assert models.resolve_model_spec("claude-sonnet").id == "_default"


def test_resolve_model_spec_none_is_default():
    assert models.resolve_model_spec(None).id == "_default"


def test_system_message_prompt_cache(monkeypatch, _all_providers):
    # Anthropic → structured content with a cache_control breakpoint
    anthropic = models.system_message("BIG STATIC PROMPT", model_id="claude-sonnet")
    assert isinstance(anthropic.content, list)
    assert anthropic.content[0]["cache_control"] == {"type": "ephemeral"}
    assert anthropic.content[0]["text"] == "BIG STATIC PROMPT"

    # OpenAI / Groq → plain string
    openai = models.system_message("BIG STATIC PROMPT", model_id="gpt-4o")
    assert openai.content == "BIG STATIC PROMPT"

    # cache=False always plain
    assert isinstance(
        models.system_message("x", model_id="claude-sonnet", cache=False).content, str
    )
