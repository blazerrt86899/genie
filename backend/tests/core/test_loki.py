"""core/loki.py — the local log-explorer shipper (CLAUDE.md §21)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from app.core import loki


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    monkeypatch.setattr(
        loki,
        "settings",
        SimpleNamespace(
            LOKI_URL="http://localhost:3100",
            LOKI_FLUSH_INTERVAL_SECONDS=2.0,
            LOKI_BATCH_SIZE=200,
            is_production=False,
        ),
    )
    while not loki._queue.empty():  # a leftover from another test must not leak
        loki._queue.get_nowait()
    loki._last_error_logged = 0.0


def test_enqueue_is_noop_without_loki_url(monkeypatch):
    monkeypatch.setattr(loki.settings, "LOKI_URL", None)
    loki.enqueue({"event": "hi", "level": "info"})
    assert loki._queue.empty()


def test_enqueue_queues_a_copy():
    event = {"event": "hi", "level": "info"}
    loki.enqueue(event)
    event["event"] = "mutated after enqueue"  # must not affect the queued copy
    queued = loki._queue.get_nowait()
    assert queued == {"event": "hi", "level": "info"}


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeClient:
    def __init__(self, *, fail: bool = False):
        self.calls: list[dict] = []
        self.fail = fail

    def post(self, url, json, timeout):  # noqa: A002 — matches httpx's signature
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.fail:
            raise ConnectionError("loki unreachable")
        return _FakeResponse()


def test_flush_groups_batch_by_level_into_loki_streams():
    client = _FakeClient()
    batch = [
        {"event": "a", "level": "info", "run_id": "r1"},
        {"event": "b", "level": "error", "agent": "web_search"},
        {"event": "c", "level": "info"},
    ]
    loki._flush(client, batch)

    assert len(client.calls) == 1
    payload = client.calls[0]["json"]
    streams = {s["stream"]["level"]: s for s in payload["streams"]}
    assert set(streams) == {"info", "error"}
    assert streams["info"]["stream"]["service"] == "genie-backend"
    assert streams["info"]["stream"]["env"] == "development"
    assert len(streams["info"]["values"]) == 2
    assert len(streams["error"]["values"]) == 1

    # each value is [nanosecond-timestamp-string, json-line]
    ts, line = streams["error"]["values"][0]
    assert ts.isdigit()
    assert json.loads(line) == {"event": "b", "level": "error", "agent": "web_search"}


def test_flush_empty_batch_does_not_call_post():
    client = _FakeClient()
    loki._flush(client, [])
    assert client.calls == []


def test_flush_failure_is_swallowed_not_raised():
    client = _FakeClient(fail=True)
    loki._flush(client, [{"event": "x", "level": "info"}])  # must not raise
    assert client.calls  # it did try
