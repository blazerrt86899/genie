"""Generated-file rendering + storage (CLAUDE.md §12, §14) — the ``file_creator``
agent's one code path for turning Markdown-authored content into a real,
downloadable file, and for serving it back.

The LLM always authors the document body in Markdown (or, for ``csv``/``json``,
the raw target text) — ``render()`` converts that into each target format's
native structure. Storage mirrors ``document_service``: bytes go straight to
S3, keyed by a precomputed id so the DB row and the S3 object agree.
"""

from __future__ import annotations

import io
import mimetypes
import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import aws
from app.db.models.generated_file import GeneratedFile
from app.db.repositories.generated_file_repo import GeneratedFileRepository

logger = structlog.get_logger(__name__)

_MIME: dict[str, str] = {
    "md": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def mime_for(fmt: str, code_ext: str | None = None) -> str:
    if fmt == "code" and code_ext:
        guessed, _ = mimetypes.guess_type(f"file.{code_ext}")
        return guessed or "text/plain"
    return _MIME.get(fmt, "text/plain")


# ─── Markdown → blocks (shared by the docx/pdf/xlsx renderers) ──────────────

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)")
_SEPARATOR_RE = re.compile(r"^:?-{1,}:?$")


def _parse_markdown_blocks(md: str) -> list[dict]:
    """A deliberately small Markdown parser — headings, paragraphs, bullet
    lists, and a GFM pipe table. Enough structure for a written-up document;
    not a general Markdown engine."""
    blocks: list[dict] = []
    lines = md.replace("\r\n", "\n").split("\n")
    para_buf: list[str] = []

    def flush_para() -> None:
        text = " ".join(para_buf).strip()
        if text:
            blocks.append({"type": "para", "text": text})
        para_buf.clear()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_para()
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading.group(1)),
                    "text": heading.group(2).strip(),
                }
            )
            i += 1
            continue
        bullet = _BULLET_RE.match(stripped)
        if bullet:
            flush_para()
            blocks.append({"type": "bullet", "text": bullet.group(1).strip()})
            i += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_para()
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(_SEPARATOR_RE.match(c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        para_buf.append(stripped)
        i += 1
    flush_para()
    return blocks


def _latin1_safe(text: str) -> str:
    """fpdf2's core fonts are Latin-1 only — swap common smart punctuation for
    its ASCII equivalent and drop anything else that won't encode, rather than
    letting a stray curly quote crash the render."""
    text = (
        text.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace("…", "...")
    )
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_docx(content: str) -> bytes:
    from docx import Document as DocxDocument

    doc = DocxDocument()
    for block in _parse_markdown_blocks(content):
        if block["type"] == "heading":
            doc.add_heading(block["text"], level=min(block["level"], 3))
        elif block["type"] == "bullet":
            doc.add_paragraph(block["text"], style="List Bullet")
        elif block["type"] == "table":
            rows = block["rows"]
            table = doc.add_table(rows=0, cols=len(rows[0]))
            table.style = "Light Grid Accent 1"
            for r in rows:
                cells = table.add_row().cells
                for idx, val in enumerate(r):
                    if idx < len(cells):
                        cells[idx].text = val
        else:
            doc.add_paragraph(block["text"])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _render_pdf(content: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    # `multi_cell` in this fpdf2 version leaves the cursor at the RIGHT edge by
    # default (only `write()` resets to the left margin) — every call below
    # pins new_x/new_y explicitly so the next line starts back at the margin.
    cell_kwargs = {"new_x": "LMARGIN", "new_y": "NEXT"}
    for block in _parse_markdown_blocks(content):
        text = _latin1_safe(block.get("text", ""))
        if block["type"] == "heading":
            size = {1: 18, 2: 15, 3: 13}.get(block["level"], 13)
            pdf.set_font("Helvetica", style="B", size=size)
            pdf.multi_cell(0, size * 0.6, text, **cell_kwargs)
            pdf.set_font("Helvetica", size=11)
            pdf.ln(1)
        elif block["type"] == "bullet":
            pdf.multi_cell(0, 6, f"-  {text}", **cell_kwargs)
        elif block["type"] == "table":
            for row in block["rows"]:
                pdf.multi_cell(0, 6, " | ".join(_latin1_safe(c) for c in row), **cell_kwargs)
        else:
            pdf.multi_cell(0, 6, text, **cell_kwargs)
            pdf.ln(2)
    return bytes(pdf.output())


def _render_xlsx(content: str) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None  # always true right after Workbook()
    ws.title = "Sheet1"
    table = next((b for b in _parse_markdown_blocks(content) if b["type"] == "table"), None)
    if table:
        for row in table["rows"]:
            ws.append(row)
    else:
        for line in content.strip().splitlines():
            if line.strip():
                ws.append([line.strip()])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def render(fmt: str, content: str) -> bytes:
    """``content`` (Markdown, or raw CSV/JSON text for those formats) → bytes
    in the target format."""
    if fmt == "docx":
        return _render_docx(content)
    if fmt == "pdf":
        return _render_pdf(content)
    if fmt == "xlsx":
        return _render_xlsx(content)
    # md / txt / csv / json / code — the LLM already wrote the target text directly
    return content.strip().encode("utf-8") + b"\n"


# ─── storage ─────────────────────────────────────────────────────────────────


async def upload(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    filename: str,
    fmt: str,
    data: bytes,
    mime_type: str,
    summary: str | None = None,
) -> GeneratedFile:
    file_id = uuid.uuid4()
    s3_key = f"{user_id}/{conversation_id}/{file_id}/{filename}"
    aws.s3().put_object(
        Bucket=settings.S3_BUCKET_NAME, Key=s3_key, Body=data, ContentType=mime_type
    )
    row = await GeneratedFileRepository(db).add(
        GeneratedFile(
            id=file_id,
            user_id=user_id,
            conversation_id=conversation_id,
            filename=filename,
            format=fmt,
            mime_type=mime_type,
            s3_key=s3_key,
            byte_size=len(data),
            summary=summary,
        )
    )
    logger.info(
        "generated_file_uploaded",
        file_id=str(file_id),
        conversation_id=str(conversation_id),
        format=fmt,
        bytes=len(data),
        s3_key=s3_key,
    )
    return row


async def download_bytes(
    db: AsyncSession, user_id: uuid.UUID, file_id: uuid.UUID
) -> tuple[GeneratedFile, bytes] | None:
    row = await GeneratedFileRepository(db).get_for_user(file_id, user_id)
    if row is None:
        return None
    obj = aws.s3().get_object(Bucket=settings.S3_BUCKET_NAME, Key=row.s3_key)
    data = obj["Body"].read()
    logger.info("generated_file_downloaded", file_id=str(file_id), bytes=len(data))
    return row, data
