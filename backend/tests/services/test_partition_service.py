"""Document partitioning — md / txt / pdf → typed elements (CLAUDE.md §10)."""

from __future__ import annotations

import pytest
from app.services.rag import partition_service as ps


def test_md_partitions_titles_and_text():
    md = (
        b"# Big Title\n\nParagraph one has enough words to be narrative text.\n\n"
        b"## Section\n\n- a\n- b"
    )
    els = ps.partition("md", md)
    types = {e.type for e in els}
    assert "Title" in types
    stats = ps.element_stats(els)
    assert stats["titles"] >= 1
    assert stats["text"] >= 1


def test_txt_partitions():
    els = ps.partition(
        "txt",
        b"This is a full sentence of plain text with several words.\n\n"
        b"Here is another paragraph, also with a reasonable number of words in it.",
    )
    assert len(els) >= 1
    assert all(e.text for e in els)


def test_empty_raises():
    with pytest.raises(ValueError):
        ps.partition("txt", b"   \n\t  ")


def test_pdf_uses_pdfminer(monkeypatch):
    class _Char:
        size = 20.0

    class _Line:
        def __iter__(self):
            return iter([_Char()])

    class _Container:
        def get_text(self):
            return "Heading Text"

        def __iter__(self):
            return iter([_Line()])

    def _fake_pages(_fh):
        return [[_Container()]]

    monkeypatch.setattr("pdfminer.high_level.extract_pages", _fake_pages)
    # isinstance checks against the real classes → patch them to accept our fakes
    monkeypatch.setattr("app.services.rag.partition_service._partition_pdf", ps._partition_pdf)
    monkeypatch.setattr("pdfminer.layout.LTTextContainer", _Container)
    monkeypatch.setattr("pdfminer.layout.LTChar", _Char)
    els = ps.partition("pdf", b"%PDF-fake")
    assert els and els[0].page == 1
