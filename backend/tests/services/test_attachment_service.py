"""Attachment file parser (CLAUDE.md §9, §14)."""

from __future__ import annotations

import pytest
from app.services import attachment_service
from app.services.attachment_service import AttachmentError, parse_upload


def test_txt_and_md_decode():
    d = parse_upload("notes.txt", b"plain text here")
    assert d.kind == "txt"
    assert d.text == "plain text here"
    assert d.char_count == 15
    assert d.token_estimate == 3

    m = parse_upload("readme.md", b"# Title\n\nbody")
    assert m.kind == "md"
    assert m.text == "# Title\n\nbody"


def test_unsupported_extension():
    with pytest.raises(AttachmentError):
        parse_upload("photo.png", b"\x89PNG")


def test_oversize_rejected():
    with pytest.raises(AttachmentError):
        parse_upload("big.txt", b"x" * (5 * 1024 * 1024 + 1))


def test_empty_text_rejected():
    with pytest.raises(AttachmentError):
        parse_upload("blank.txt", b"   \n\t ")


def test_pdf_uses_pypdf(monkeypatch):
    class _Page:
        def extract_text(self):
            return "page one text"

    class _Reader:
        def __init__(self, _fh):
            self.pages = [_Page(), _Page()]

    monkeypatch.setattr("pypdf.PdfReader", _Reader)
    d = parse_upload("doc.pdf", b"%PDF-1.4 fake")
    assert d.kind == "pdf"
    assert "page one text" in d.text


def test_pdf_read_error_is_attachment_error(monkeypatch):
    def _boom(_fh):
        raise RuntimeError("corrupt")

    monkeypatch.setattr("pypdf.PdfReader", _boom)
    with pytest.raises(AttachmentError):
        parse_upload("doc.pdf", b"garbage")


async def test_list_for_ids_skips_bad_uuids(monkeypatch):
    seen = {}

    class _Repo:
        def __init__(self, _db): ...

        async def list_for_user_ids(self, user_id, ids):
            seen["ids"] = ids
            return []

    monkeypatch.setattr(attachment_service, "AttachmentRepository", _Repo)
    await attachment_service.list_for_ids(None, "u", ["not-a-uuid", ""])
    assert seen["ids"] == []
