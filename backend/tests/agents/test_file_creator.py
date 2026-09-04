"""File Creator agent (CLAUDE.md §12)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.agents.file_creator import agent as fc
from app.agents.file_creator.schemas import FileSpec
from langchain_core.messages import HumanMessage


def _state(**kw):
    base = {
        "messages": [HumanMessage(content="write me a summary of our roadmap")],
        "user_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "model": None,
        "intermediate_results": {},
    }
    base.update(kw)
    return base


def _task(desc="write a PDF report of the roadmap", depends_on=None):
    return {
        "id": "t2",
        "description": desc,
        "agent": "file_creator",
        "depends_on": depends_on or [],
    }


class FakeUploadedRow:
    def __init__(self, filename, fmt, mime_type, data, summary):
        self.id = uuid.uuid4()
        self.filename = filename
        self.format = fmt
        self.mime_type = mime_type
        self.byte_size = len(data)
        self.summary = summary


def _patch_common(monkeypatch, *, spec: FileSpec, body: str):
    class SpecModel:
        async def ainvoke(self, _messages):
            return {"parsed": spec, "raw": SimpleNamespace()}

    class ContentModel:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content=body)

    monkeypatch.setattr(fc, "get_utility_model", lambda **_: SimpleNamespace(
        with_structured_output=lambda *_a, **_k: SpecModel()
    ))
    monkeypatch.setattr(fc, "get_chat_model", lambda **_: ContentModel())

    async def fake_upload(_db, _user_id, _conv_id, *, filename, fmt, data, mime_type, summary=None):
        return FakeUploadedRow(filename, fmt, mime_type, data, summary)

    monkeypatch.setattr(fc.file_service, "upload", fake_upload)

    class _Session:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(fc, "get_sessionmaker", lambda: (lambda: _Session()))


async def test_creates_a_pdf_and_returns_a_file(monkeypatch):
    _patch_common(
        monkeypatch,
        spec=FileSpec(filename="Roadmap Report", format="pdf"),
        body="# Roadmap\n\nWe are shipping X, Y, Z this quarter.",
    )
    res = await fc.run_file_creator(_state(), _task())
    assert res.files, "expected a file in AgentResult.files"
    f = res.files[0]
    assert f["filename"] == "Roadmap-Report.pdf"
    assert f["mime_type"] == "application/pdf"
    assert "Roadmap-Report.pdf" in res.summary


async def test_defaults_to_markdown_on_spec_failure(monkeypatch):
    class BrokenSpecModel:
        async def ainvoke(self, _messages):
            raise RuntimeError("boom")

    monkeypatch.setattr(fc, "get_utility_model", lambda **_: SimpleNamespace(
        with_structured_output=lambda *_a, **_k: BrokenSpecModel()
    ))

    class ContentModel:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="Just some notes.")

    monkeypatch.setattr(fc, "get_chat_model", lambda **_: ContentModel())

    async def fake_upload(_db, _user_id, _conv_id, *, filename, fmt, data, mime_type, summary=None):
        return FakeUploadedRow(filename, fmt, mime_type, data, summary)

    monkeypatch.setattr(fc.file_service, "upload", fake_upload)

    class _Session:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(fc, "get_sessionmaker", lambda: (lambda: _Session()))

    res = await fc.run_file_creator(_state(), _task(desc="just jot this down"))
    assert res.files[0]["filename"].endswith(".md")


async def test_gathers_context_from_dependency_findings(monkeypatch):
    _patch_common(
        monkeypatch,
        spec=FileSpec(filename="notes", format="md"),
        body="body",
    )
    captured: dict = {}

    class ContentModel:
        async def ainvoke(self, messages):
            captured["prompt"] = messages[0].content
            return SimpleNamespace(content="body")

    monkeypatch.setattr(fc, "get_chat_model", lambda **_: ContentModel())

    state = _state(
        intermediate_results={
            "t1": {
                "agent": "web_search",
                "summary": "Found three JS test frameworks: Jest, Vitest, Playwright.",
            }
        }
    )
    task = _task(depends_on=["t1"])
    await fc.run_file_creator(state, task)
    assert "Jest" in captured["prompt"]


async def test_raises_on_empty_content(monkeypatch):
    _patch_common(monkeypatch, spec=FileSpec(filename="empty", format="txt"), body="   ")
    with pytest.raises(RuntimeError):
        await fc.run_file_creator(_state(), _task())
