"""Guardrail graph nodes.

``input_guard_node`` runs first (``START → input_guard → prompt_enhancer``): it
scans the user's message + attachment text, **redacts secrets and card/SSN
numbers before anything reaches an LLM**, keeps ordinary PII (the user's own
email is often the point), and flags what it found so the UI can warn.

``scrub_output`` is called from ``validator_node`` — a last deterministic pass
that strips any secret the model echoed back.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage

from app.agents.events import emit
from app.config import settings
from app.core import guardrails

logger = structlog.get_logger(__name__)

_REDACT_KINDS = {"ssn", "credit_card"}  # PII we redact even though it's not a "secret"


def _last_human(messages: list):
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return msg
    return None


async def input_guard_node(state: dict) -> dict:
    if not settings.GUARDRAILS_ENABLED or not settings.GUARDRAIL_INPUT_ENABLED:
        return {}

    try:
        msg = _last_human(state.get("messages", []))
        text = str(msg.content) if msg is not None else ""
        attachments = list(state.get("attachments") or [])

        findings = guardrails.scan(text)
        att_findings = [guardrails.scan(a.get("text") or "") for a in attachments]

        if not findings and not any(att_findings):
            return {}

        def _to_redact(fs):
            return [f for f in fs if f.severity == "secret" or f.kind in _REDACT_KINDS]

        out: dict = {}

        msg_redactions = _to_redact(findings)
        if msg_redactions and msg is not None:
            redacted = guardrails.redact(text, msg_redactions)
            out["messages"] = [HumanMessage(content=redacted, id=getattr(msg, "id", None))]

        if any(_to_redact(fs) for fs in att_findings):
            out["attachments"] = [
                {**a, "text": guardrails.redact(a.get("text") or "", _to_redact(fs))}
                for a, fs in zip(attachments, att_findings, strict=False)
            ]

        all_findings = list(findings) + [f for fs in att_findings for f in fs]
        redacted_kinds = sorted({
            f.kind for f in all_findings
            if f.severity == "secret" or f.kind in _REDACT_KINDS
        })
        flagged_kinds = sorted({
            f.kind for f in all_findings
            if f.severity == "pii" and f.kind not in _REDACT_KINDS
        })

        note = _user_note(redacted_kinds, flagged_kinds, all_findings)
        out["metadata"] = {
            **(state.get("metadata") or {}),
            "guardrail": {
                "redacted": redacted_kinds,
                "flagged": flagged_kinds,
                "message": note,
            },
        }

        logger.info(
            "guardrail_input",
            redacted=redacted_kinds,
            flagged=flagged_kinds,
            findings=len(all_findings),
        )
        await emit(
            "guardrail",
            {
                "types": redacted_kinds + flagged_kinds,
                "redacted": bool(redacted_kinds),
                "message": note,
            },
        )
        return out
    except Exception:  # noqa: BLE001 — fail open, never block a turn on the guard
        logger.warning("guardrail_error", stage="input", exc_info=True)
        return {}


def _user_note(redacted: list[str], flagged: list[str], findings: list) -> str:
    parts = []
    if redacted:
        summary = guardrails.summarize([f for f in findings if f.kind in redacted])
        parts.append(f"Hid {summary} before sending — never share live secrets or card numbers.")
    if flagged:
        summary = guardrails.summarize([f for f in findings if f.kind in flagged])
        parts.append(f"Heads-up: your message contains {summary}.")
    return " ".join(parts)


def scrub_output(text: str) -> tuple[str, list[str]]:
    """Redact any secret the model echoed back. Returns ``(clean_text, kinds)``."""
    if not settings.GUARDRAILS_ENABLED or not settings.GUARDRAIL_OUTPUT_ENABLED or not text:
        return text, []
    try:
        findings = [f for f in guardrails.scan(text) if f.severity == "secret"]
        if not findings:
            return text, []
        kinds = sorted({f.kind for f in findings})
        logger.warning("guardrail_output_redacted", kinds=kinds)
        return guardrails.redact(text, findings), kinds
    except Exception:  # noqa: BLE001
        logger.warning("guardrail_error", stage="output", exc_info=True)
        return text, []
