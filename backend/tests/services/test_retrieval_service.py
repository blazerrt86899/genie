"""Project KB retrieval — strategy dispatch + RRF fusion (CLAUDE.md §10)."""

from __future__ import annotations

import uuid

import pytest
from app.schemas.rag import RagSettings
from app.services.rag import retrieval_service as rs


@pytest.fixture(autouse=True)
def _fake_embed(monkeypatch):
    async def _embed(texts):
        return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(rs.embedder, "embed_batch", _embed)


def _chunk(cid, text, sim=0.8):
    return {
        "id": cid,
        "content": text,
        "metadata": {"heading": "H"},
        "document_id": "doc1",
        "similarity": sim,
        "score": sim,
    }


async def test_vector_strategy(monkeypatch):
    async def _vec(db, pid, uid, qvec, s):
        return [_chunk("a", "alpha"), _chunk("b", "beta")]

    monkeypatch.setattr(rs, "_vector", _vec)
    monkeypatch.setattr(rs, "_fetch_filenames", lambda db, pid: _fname())

    out = await rs.retrieve(
        None,
        uuid.uuid4(),
        uuid.uuid4(),
        "q",
        RagSettings(search_strategy="vector", final_context_size=3),
    )
    assert [c["content"] for c in out] == ["alpha", "beta"]
    assert out[0]["filename"] == "report.pdf"


async def test_hybrid_strategy(monkeypatch):
    called = {}

    async def _hyb(db, pid, uid, q, qvec, s):
        called["q"] = q
        return [_chunk("a", "alpha")]

    monkeypatch.setattr(rs, "_hybrid", _hyb)
    monkeypatch.setattr(rs, "_fetch_filenames", lambda db, pid: _fname())

    out = await rs.retrieve(
        None, uuid.uuid4(), uuid.uuid4(), "the question", RagSettings(search_strategy="hybrid")
    )
    assert called["q"] == "the question"
    assert len(out) == 1


async def test_multi_query_fuses_and_caps(monkeypatch):
    async def _para(q, n):
        return [q, "rephrase A", "rephrase B"]

    async def _vec(db, pid, uid, qvec, s):
        # each query returns a different top chunk + a shared one
        return [_chunk("shared", "shared text"), _chunk(str(uuid.uuid4()), "unique")]

    monkeypatch.setattr(rs, "_paraphrases", _para)
    monkeypatch.setattr(rs, "_vector", _vec)
    monkeypatch.setattr(rs, "_fetch_filenames", lambda db, pid: _fname())

    out = await rs.retrieve(
        None,
        uuid.uuid4(),
        uuid.uuid4(),
        "q",
        RagSettings(search_strategy="multi_query_vector", num_queries=3, final_context_size=3),
    )
    assert out[0]["content"] == "shared text"  # appears in every list → highest RRF


async def _fname():
    return {"doc1": "report.pdf"}


def test_rrf_fuse_ranks_common_hits_first():
    a = [{"id": "x"}, {"id": "y"}]
    b = [{"id": "y"}, {"id": "z"}]
    fused = rs._rrf_fuse([a, b])
    assert fused[0]["id"] == "y"
