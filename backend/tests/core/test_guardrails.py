"""core/guardrails.py — the deterministic secret/PII scanner."""

from __future__ import annotations

from app.core import guardrails as g


def _kinds(text: str) -> set[str]:
    return {f.kind for f in g.scan(text)}


def test_detects_secrets():
    assert "api_key" in _kinds("key is sk-abc123def456ghi789jkl000")
    assert "api_key" in _kinds("token ghp_0123456789abcdefghijABCD")
    assert "aws_key" in _kinds("AKIA1234567890ABCDEF")
    assert "google_key" in _kinds("AIza" + "b" * 35)
    assert "jwt" in _kinds(
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpM"
    )
    assert "private_key" in _kinds(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nbody\n-----END OPENSSH PRIVATE KEY-----"
    )
    assert "url_creds" in _kinds("postgres://user:hunter2pw@host/db")
    assert "password_kv" in _kinds("password = hunter2secret")


def test_detects_pii():
    assert "email" in _kinds("reach me at jane.doe@example.co.uk")
    assert "phone" in _kinds("call +1 (415) 555-2671 today")
    assert "ssn" in _kinds("ssn 123-45-6789")
    assert "ip" in _kinds("server at 10.1.2.3")


def test_credit_card_luhn():
    assert "credit_card" in _kinds("card 4111 1111 1111 1111")
    assert "credit_card" not in _kinds("not a card 4111 1111 1111 1112")


def test_severity_split():
    findings = g.scan("sk-abc123def456ghi789jkl and a@b.com")
    sev = {f.kind: f.severity for f in findings}
    assert sev["api_key"] == "secret"
    assert sev["email"] == "pii"


def test_redact_only_touches_matches():
    text = "here is sk-abc123def456ghi789jkl000 — keep the rest"
    out = g.redact(text, g.scan(text))
    assert "sk-abc123" not in out
    assert "keep the rest" in out
    assert "[REDACTED_API_KEY]" in out


def test_overlap_resolution_secret_wins():
    # a JWT looks a bit like other things — only one finding for its span
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpM"
    spans = [(f.start, f.end) for f in g.scan(jwt)]
    assert len(spans) == 1


def test_summarize():
    assert g.summarize([]) is None
    one = g.scan("token sk-abc123def456ghi789jkl000")
    assert g.summarize(one) == "an API key"
    two = g.summarize(g.scan("a@b.com and c@d.com")) or ""
    assert "email address" in two


def test_clean_text_no_findings():
    assert g.scan("how do threads differ from processes in python") == []
