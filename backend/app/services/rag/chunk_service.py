"""Pipeline phase 2 — group elements into retrieval chunks (CLAUDE.md §10).

Structure-aware: `unstructured.chunking.title.chunk_by_title` keeps a heading
with its body and never splits mid-element unless an element alone exceeds the
size cap. Sizes come from the project's `RagSettings`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from app.services.rag.partition_service import Element

logger = structlog.get_logger(__name__)

_ENC = None


def _token_count(text: str) -> int:
    global _ENC
    if _ENC is None:
        import tiktoken

        _ENC = tiktoken.get_encoding("cl100k_base")
    return len(_ENC.encode(text))


@dataclass
class Chunk:
    index: int
    text: str
    token_count: int
    metadata: dict = field(default_factory=dict)


def chunk(elements: list[Element], *, size: int, overlap: int) -> list[Chunk]:
    from unstructured.chunking.title import chunk_by_title
    from unstructured.documents.elements import ListItem, NarrativeText, Title

    _cls = {"Title": Title, "ListItem": ListItem, "NarrativeText": NarrativeText}
    u_elements = [
        _cls.get(el.type, NarrativeText)(text=el.text, metadata=_meta(el)) for el in elements
    ]

    out: list[Chunk] = []
    for ch in chunk_by_title(
        u_elements,
        max_characters=size,
        overlap=min(overlap, size // 2),
        combine_text_under_n_chars=max(120, size // 6),
    ):
        text = str(ch).strip()
        if len(text) < 12:  # a lone heading / stray fragment — not worth a vector
            continue
        out.append(
            Chunk(
                index=len(out),
                text=text,
                token_count=_token_count(text),
                metadata={
                    "page": _chunk_page(ch) or _first_page(elements),
                    "element_types": _types_in(ch),
                    "heading": _heading(ch),
                },
            )
        )
    logger.info("chunk_done", chunks=len(out), size=size, overlap=overlap)
    return out


def _meta(el: Element):
    from unstructured.documents.elements import ElementMetadata

    return ElementMetadata(page_number=el.page) if el.page else ElementMetadata()


def _first_page(elements: list[Element]) -> int | None:
    return next((el.page for el in elements if el.page), None)


def _chunk_page(ch) -> int | None:
    """`metadata.page_number` may be an int, a list, or missing — normalise it."""
    pn = getattr(getattr(ch, "metadata", None), "page_number", None)
    if isinstance(pn, int):
        return pn
    if isinstance(pn, (list, tuple, set)) and pn:
        return sorted(pn)[0]
    # fall back to the first page across the chunk's source elements
    origs = getattr(getattr(ch, "metadata", None), "orig_elements", None) or []
    for e in origs:
        p = getattr(getattr(e, "metadata", None), "page_number", None)
        if isinstance(p, int):
            return p
    return None


def _types_in(ch) -> list[str]:
    origs = getattr(getattr(ch, "metadata", None), "orig_elements", None) or []
    return sorted({type(e).__name__ for e in origs}) or [type(ch).__name__]


def _heading(ch) -> str | None:
    from unstructured.documents.elements import Title

    origs = getattr(getattr(ch, "metadata", None), "orig_elements", None) or []
    for e in origs:
        if isinstance(e, Title):
            return str(e)[:120]
    return None
