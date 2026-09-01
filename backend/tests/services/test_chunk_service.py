"""Chunking — elements → retrieval chunks (CLAUDE.md §10)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.rag import chunk_service
from app.services.rag.chunk_service import chunk
from app.services.rag.partition_service import Element


def _elements(n_paras: int, words: int = 60) -> list[Element]:
    out = [Element(type="Title", text="Document Title")]
    for i in range(n_paras):
        out.append(Element(type="NarrativeText", text=f"para {i} " + ("word " * words)))
    return out


def test_chunks_have_index_tokens_and_metadata():
    chunks = chunk(_elements(6), size=1000, overlap=100)
    assert chunks
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.token_count > 0 for c in chunks)
    assert all("element_types" in c.metadata for c in chunks)


def test_larger_size_makes_fewer_chunks():
    small = chunk(_elements(10), size=600, overlap=50)
    big = chunk(_elements(10), size=3000, overlap=50)
    assert len(big) < len(small)


def test_tiny_fragments_dropped():
    chunks = chunk([Element(type="Title", text="Hi")], size=1000, overlap=0)
    assert chunks == []


def test_chunk_page_handles_int_list_and_missing():
    # unstructured PDF chunks carry page_number as a bare int → must not iterate it
    assert chunk_service._chunk_page(SimpleNamespace(metadata=SimpleNamespace(page_number=3))) == 3
    assert (
        chunk_service._chunk_page(SimpleNamespace(metadata=SimpleNamespace(page_number=[5, 2])))
        == 2
    )
    none_md = SimpleNamespace(metadata=SimpleNamespace(page_number=None))
    assert chunk_service._chunk_page(none_md) is None


def test_pdf_pages_survive_chunking():
    els = [
        Element(type="Title", text="Manjeet SRE CV", page=1),
        Element(type="NarrativeText", text="Senior SRE. " + ("kubernetes " * 40), page=1),
        Element(type="NarrativeText", text="Experience. " + ("terraform " * 40), page=2),
    ]
    chunks = chunk(els, size=1000, overlap=50)  # must not raise "'int' object is not iterable"
    assert chunks
    assert all(isinstance(c.metadata["page"], int) for c in chunks)
