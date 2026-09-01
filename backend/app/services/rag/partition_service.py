"""Pipeline phase 1 — partition a document into typed elements (CLAUDE.md §10).

`md` / `txt` go through `unstructured` (Title / NarrativeText / ListItem / …).
`pdf` goes through `pdfminer.six` directly (unstructured's own "fast" backend,
without the heavy `unstructured_inference` ML dependency) with a light
font-size / bullet heuristic for element types.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

_BULLET = re.compile(r"^\s*([-*•‣◦·]|\d+[.)])\s+")


@dataclass
class Element:
    type: str  # Title | NarrativeText | ListItem | Other
    text: str
    page: int | None = None


_STAT_BUCKET = {
    "Title": "titles",
    "NarrativeText": "text",
    "ListItem": "text",
    "Table": "tables",
    "Image": "images",
}


def element_stats(elements: list[Element]) -> dict[str, int]:
    """The "Elements Discovered" grid: text / titles / tables / images / other."""
    out = {"text": 0, "titles": 0, "tables": 0, "images": 0, "other": 0}
    for el in elements:
        out[_STAT_BUCKET.get(el.type, "other")] += 1
    return out


# ─── md / txt via unstructured ──────────────────────────────────────────────

_UNSTRUCTURED_TYPE = {
    "Title": "Title",
    "NarrativeText": "NarrativeText",
    "Text": "NarrativeText",
    "UncategorizedText": "NarrativeText",
    "ListItem": "ListItem",
    "Table": "Table",
    "Image": "Image",
}


def _partition_unstructured(kind: str, text: str) -> list[Element]:
    if kind == "md":
        from unstructured.partition.md import partition_md as fn
    else:
        from unstructured.partition.text import partition_text as fn
    out: list[Element] = []
    for el in fn(text=text):
        body = str(el).strip()
        if not body:
            continue
        out.append(Element(type=_UNSTRUCTURED_TYPE.get(el.category, "NarrativeText"), text=body))
    return out


# ─── pdf via pdfminer.six ───────────────────────────────────────────────────


def _partition_pdf(data: bytes) -> list[Element]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTTextContainer

    elements: list[Element] = []
    sizes: list[float] = []
    raw: list[tuple[int, str, float]] = []  # (page, text, avg_font_size)

    for page_no, layout in enumerate(extract_pages(io.BytesIO(data)), start=1):
        for obj in layout:
            if not isinstance(obj, LTTextContainer):
                continue
            body = obj.get_text().strip()
            if not body:
                continue
            fs = [c.size for line in obj for c in line if isinstance(c, LTChar)]
            avg = sum(fs) / len(fs) if fs else 0.0
            if avg:
                sizes.append(avg)
            raw.append((page_no, re.sub(r"[ \t]*\n[ \t]*", " ", body).strip(), avg))

    median = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
    for page_no, body, avg in raw:
        if _BULLET.match(body):
            etype = "ListItem"
        elif avg and avg >= median * 1.15 and len(body) < 140:
            etype = "Title"
        else:
            etype = "NarrativeText"
        elements.append(Element(type=etype, text=body, page=page_no))
    return elements


def partition(kind: str, data: bytes) -> list[Element]:
    if kind == "pdf":
        elements = _partition_pdf(data)
    else:
        elements = _partition_unstructured(kind, data.decode("utf-8", "replace"))
    if not elements:
        raise ValueError("no extractable text in the document")
    logger.info(
        "partition_done", kind=kind, elements=len(elements), stats=element_stats(elements)
    )
    return elements
