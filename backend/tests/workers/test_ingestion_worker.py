"""ingest_document — pipeline happy path + idempotency + failure (CLAUDE.md §4.5, §10)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.workers import ingestion_worker as iw


class _Doc:
    def __init__(self, **kw):
        self.id = kw.get("id", uuid.uuid4())
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.kind = "md"
        self.s3_key = "k"
        self.status = "queued"
        self.phase = "upload"
        self.processed_at = None


class _DocRepo:
    def __init__(self, _db):
        self.calls = []

    async def get(self, did):
        return _STATE["doc"]

    async def set_phase(self, did, phase, **kw):
        _STATE["phases"].append((phase, kw.get("status", "processing")))
        _STATE["doc"].phase = phase
        if kw.get("status") == "failed":
            _STATE["doc"].status = "failed"

    async def mark_ready(self, did, stats):
        _STATE["doc"].status = "ready"
        _STATE["doc"].processed_at = "now"


class _ChunkRepo:
    def __init__(self, _db): ...

    async def bulk_insert(self, rows):
        _STATE["inserted"] = len(rows)
        return len(rows)


class _ProjRepo:
    def __init__(self, _db): ...

    async def get_for_user(self, pid, uid):
        return SimpleNamespace(rag_settings={})


_STATE: dict = {}


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _STATE.clear()
    _STATE.update(doc=_Doc(), phases=[], inserted=0)

    class _CM:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(iw, "get_sessionmaker", lambda: (lambda: _CM()))
    monkeypatch.setattr(iw, "DocumentRepository", _DocRepo)
    monkeypatch.setattr(iw, "DocumentChunkRepository", _ChunkRepo)
    monkeypatch.setattr(iw, "ProjectRepository", _ProjRepo)
    monkeypatch.setattr(
        iw.aws, "s3", lambda: SimpleNamespace(
            get_object=lambda **kw: {"Body": SimpleNamespace(read=lambda: b"# T\n\nbody text here")}
        )
    )
    monkeypatch.setattr(
        iw.partition_service, "partition",
        lambda kind, data: [iw.partition_service.Element(type="NarrativeText", text="body " * 40)],
    )
    monkeypatch.setattr(iw.partition_service, "element_stats", lambda els: {"text": 1})
    monkeypatch.setattr(
        iw.chunk_service, "chunk",
        lambda els, **kw: [
            iw.chunk_service.Chunk(index=0, text="body " * 40, token_count=40, metadata={})
        ],
    )

    async def _embed(texts):
        return [[0.0] * 1536 for _ in texts]

    monkeypatch.setattr(iw.embedder, "embed_batch", _embed)

    async def _pub(*a, **k):
        return None

    monkeypatch.setattr(iw, "_publish", _pub)


async def test_happy_path_marks_ready():
    await iw.ingest_document(str(_STATE["doc"].id))
    assert _STATE["doc"].status == "ready"
    assert _STATE["doc"].processed_at is not None
    assert _STATE["inserted"] == 1
    assert [p for p, _ in _STATE["phases"]] == ["partition", "chunk", "vectorize", "store"]


async def test_idempotent_skip_when_ready():
    _STATE["doc"].status = "ready"
    _STATE["doc"].processed_at = "earlier"
    await iw.ingest_document(str(_STATE["doc"].id))
    assert _STATE["phases"] == []  # nothing ran


async def test_failure_marks_failed(monkeypatch):
    def _boom(kind, data):
        raise ValueError("bad pdf")

    monkeypatch.setattr(iw.partition_service, "partition", _boom)
    await iw.ingest_document(str(_STATE["doc"].id))
    assert _STATE["doc"].status == "failed"
