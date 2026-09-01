"""document_service.create_and_enqueue — S3 put + SQS enqueue (CLAUDE.md §10, §14)."""

from __future__ import annotations

import uuid

import pytest
from app.services import document_service as ds
from app.services.document_service import DocumentError


class _S3:
    calls: list = []

    def put_object(self, **kw):
        _S3.calls.append(("put", kw["Key"]))

    def delete_object(self, **kw):
        _S3.calls.append(("del", kw["Key"]))


class _SQS:
    sent: list = []

    def send_message(self, **kw):
        _SQS.sent.append(kw["MessageBody"])


class _Repo:
    def __init__(self, _db): ...

    async def add(self, obj):
        return obj


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    _S3.calls = []
    _SQS.sent = []
    monkeypatch.setattr(ds.aws, "s3", lambda: _S3())
    monkeypatch.setattr(ds.aws, "sqs", lambda: _SQS())
    monkeypatch.setattr(ds, "DocumentRepository", _Repo)
    monkeypatch.setattr(ds.settings, "S3_BUCKET_NAME", "b")
    monkeypatch.setattr(ds.settings, "SQS_QUEUE_URL", "q")


async def test_create_and_enqueue_uploads_then_queues():
    doc = await ds.create_and_enqueue(
        None, uuid.uuid4(), uuid.uuid4(), "notes.md", b"# hi\n\nbody"
    )
    assert doc.kind == "md"
    assert _S3.calls and _S3.calls[0][0] == "put"
    assert _SQS.sent and "ingest_document" in _SQS.sent[0]


async def test_bad_type_rejected():
    with pytest.raises(DocumentError):
        await ds.create_and_enqueue(None, uuid.uuid4(), uuid.uuid4(), "a.png", b"x")


async def test_oversize_rejected(monkeypatch):
    monkeypatch.setattr(ds.settings, "DOCUMENT_MAX_MB", 0)
    with pytest.raises(DocumentError):
        await ds.create_and_enqueue(None, uuid.uuid4(), uuid.uuid4(), "a.txt", b"x" * 10)
