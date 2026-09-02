"""input_guard_node + the validator output guard."""

from __future__ import annotations

from app.agents.guardrails import nodes as gnodes
from app.agents.guardrails.nodes import input_guard_node, scrub_output
from langchain_core.messages import HumanMessage


def _state(text: str, attachments=None):
    return {
        "messages": [HumanMessage(content=text, id="m1")],
        "attachments": attachments or [],
        "metadata": {},
    }


async def test_redacts_a_secret_and_flags_pii():
    st = _state("here is my key sk-abc123def456ghi789jkl000 and email me at x@y.com")
    out = await input_guard_node(st)

    assert "sk-abc123" not in out["messages"][0].content
    assert "[REDACTED_API_KEY]" in out["messages"][0].content
    assert "x@y.com" in out["messages"][0].content  # PII kept

    gr = out["metadata"]["guardrail"]
    assert "api_key" in gr["redacted"]
    assert "email" in gr["flagged"]
    assert "API key" in gr["message"]


async def test_clean_message_is_a_noop():
    assert await input_guard_node(_state("how do processes differ from threads")) == {}


async def test_redacts_attachment_text():
    st = _state(
        "check the attached config",
        attachments=[{"filename": "c.env", "kind": "txt", "text": "TOKEN=supersecretvalue123"}],
    )
    out = await input_guard_node(st)
    assert "supersecretvalue" not in out["attachments"][0]["text"]


async def test_fails_open_on_scan_error(monkeypatch):
    monkeypatch.setattr(gnodes.guardrails, "scan", lambda _t: (_ for _ in ()).throw(RuntimeError()))
    assert await input_guard_node(_state("anything")) == {}


async def test_disabled_via_settings(monkeypatch):
    monkeypatch.setattr(gnodes.settings, "GUARDRAIL_INPUT_ENABLED", False)
    assert await input_guard_node(_state("key sk-abc123def456ghi789jkl000")) == {}


def test_scrub_output_redacts_a_leaked_secret():
    clean, kinds = scrub_output("the token is ghp_0123456789abcdefghijABCD by the way")
    assert "ghp_" not in clean
    assert kinds == ["api_key"]


def test_scrub_output_leaves_pii_alone():
    text = "example: email user@example.com"
    clean, kinds = scrub_output(text)
    assert clean == text and kinds == []
