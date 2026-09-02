"""Deterministic input/output guardrails (CLAUDE.md §4, §9).

Pure functions, no I/O. Scan text for **secrets** (API keys, tokens, private
keys, credentials) and **PII** (email, phone, SSN, card numbers, IPs); the graph
nodes in ``app/agents/guardrails/`` redact the sensitive spans *before* any text
reaches an external LLM and warn the user.

Regex-first by design — fast, deterministic, zero cost, no NER model. Names and
physical addresses are out of scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Value prefixes that betray a secret regardless of context. `core/logging.py`
# imports this so the two stay in sync.
_SECRET_VALUE_PREFIXES: tuple[str, ...] = ("bearer ", "sk_", "sk-", "whsec_", "eyj")

_URL_CREDS = re.compile(r"[a-z][a-z0-9+.\-]*://[^:/@\s]+:[^@/\s]{3,}@", re.I)


@dataclass(frozen=True)
class Finding:
    kind: str  # api_key | aws_key | google_key | slack_token | jwt | private_key |
    #            password_kv | url_creds | email | phone | ssn | credit_card | ip
    severity: str  # "secret" | "pii"
    start: int
    end: int
    label: str  # redaction placeholder


_LABELS: dict[str, str] = {
    "api_key": "[REDACTED_API_KEY]",
    "aws_key": "[REDACTED_AWS_KEY]",
    "google_key": "[REDACTED_API_KEY]",
    "slack_token": "[REDACTED_TOKEN]",
    "jwt": "[REDACTED_JWT]",
    "private_key": "[REDACTED_PRIVATE_KEY]",
    "password_kv": "[REDACTED_CREDENTIAL]",
    "url_creds": "[REDACTED_URL_CREDENTIAL]",
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "ssn": "[REDACTED_SSN]",
    "credit_card": "[REDACTED_CARD]",
    "ip": "[IP]",
}

_SECRET_KINDS = frozenset(
    {"api_key", "aws_key", "google_key", "slack_token", "jwt", "private_key",
     "password_kv", "url_creds"}
)

# (kind, compiled pattern). Order matters only for the human-readable summary.
_PRIVATE_KEY = (
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]+?"
    r"-----END (?:[A-Z ]+ )?PRIVATE KEY-----"
)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(_PRIVATE_KEY)),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("api_key", re.compile(r"\b(?:sk|pk|rk)[-_](?:live|test|proj)?[-_]?[0-9A-Za-z]{16,}\b")),
    ("api_key", re.compile(r"\bgh[opsu]_[0-9A-Za-z]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.eyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\b")),
    ("url_creds", _URL_CREDS),
    ("password_kv", re.compile(
        r"(?i)\b(?:password|passwd|pwd|api[_-]?key|apikey|secret|token|access[_-]?key)\b\s*[:=]\s*[\"']?([^\s\"']{6,})"
    )),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b\d(?:[ -]?\d){12,18}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"(?<![\w.])\+?\d[\d\s().\-]{8,}\d(?![\w.])")),
    ("ip", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
]


def _luhn_ok(digits: str) -> bool:
    nums = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total, parity = 0, len(nums) % 2
    for i, n in enumerate(nums):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def scan(text: str) -> list[Finding]:
    """All secret/PII findings in ``text``, overlaps resolved (secret wins)."""
    if not text:
        return []
    raw: list[Finding] = []
    for kind, pat in _PATTERNS:
        for m in pat.finditer(text):
            if kind == "credit_card" and not _luhn_ok(m.group(0)):
                continue
            sev = "secret" if kind in _SECRET_KINDS else "pii"
            raw.append(Finding(kind, sev, m.start(), m.end(), _LABELS[kind]))

    # Drop a finding fully contained in / overlapping an earlier, higher-priority
    # one. "secret" beats "pii"; longer span beats shorter.
    raw.sort(key=lambda f: (f.severity != "secret", -(f.end - f.start), f.start))
    kept: list[Finding] = []
    for f in raw:
        if not any(f.start < k.end and k.start < f.end for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)


def redact(text: str, findings: list[Finding]) -> str:
    """Replace each finding's span with its label (right-to-left, spans stable)."""
    out = text
    for f in sorted(findings, key=lambda f: f.start, reverse=True):
        out = out[: f.start] + f.label + out[f.end :]
    return out


_PLURAL = {
    "api_key": "API key", "aws_key": "AWS key", "google_key": "API key",
    "slack_token": "Slack token", "jwt": "JWT", "private_key": "private key",
    "password_kv": "credential", "url_creds": "URL credential", "email": "email address",
    "phone": "phone number", "ssn": "SSN", "credit_card": "card number", "ip": "IP address",
}


def summarize(findings: list[Finding]) -> str | None:
    """'an API key and 2 email addresses' — for the user-facing warning."""
    if not findings:
        return None
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.kind] = counts.get(f.kind, 0) + 1
    parts: list[str] = []
    for kind, n in counts.items():
        name = _PLURAL.get(kind, kind.replace("_", " "))
        parts.append(name if n == 1 else f"{n} {name}s")
    if len(parts) == 1:
        head = parts[0]
        an = head[0].lower() in "aeiou" or head[:3] in ("API", "AWS", "SSN")
        return f"an {head}" if an else f"a {head}"
    return ", ".join(parts[:-1]) + f" and {parts[-1]}"
