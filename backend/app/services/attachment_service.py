"""Composer file attachments — parse + persist (CLAUDE.md §9, §14).

Text-only. ``parse_upload`` is pure (extension → normalized text) so it's trivially
testable; the DB-facing helpers are the one code path every caller (the endpoint,
``chat_service``, tests) goes through. The extracted text is injected into a
single turn's prompts — see ``agents/supervisor/nodes.py:_format_attachments``.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.attachment import Attachment
from app.db.repositories.attachment_repo import AttachmentRepository

logger = structlog.get_logger(__name__)

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_KINDS: dict[str, str] = {".pdf": "pdf", ".txt": "txt", ".md": "md"}


class AttachmentError(ValueError):
    """A file couldn't be accepted (bad type / too big / no text)."""


@dataclass(frozen=True)
class ParsedDocument:
    kind: str
    text: str
    char_count: int
    token_estimate: int  # ~= chars / 4


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 — pypdf raises a zoo of errors
        raise AttachmentError("could not read the PDF") from exc


def parse_upload(filename: str, data: bytes) -> ParsedDocument:
    """Extension → normalized plain text. Raises ``AttachmentError`` on anything
    we can't accept."""
    ext = Path(filename or "").suffix.lower()
    if ext not in _KINDS:
        raise AttachmentError("unsupported file type — pdf, txt or md only")
    if len(data) > _MAX_BYTES:
        raise AttachmentError("file too large (5 MB max)")

    kind = _KINDS[ext]
    text = data.decode("utf-8", "replace") if kind != "pdf" else _extract_pdf(data)
    text = text.strip()
    if not text:
        raise AttachmentError("no extractable text in the file")

    logger.info("attachment_parsed", kind=kind, char_count=len(text))
    return ParsedDocument(kind, text, len(text), len(text) // 4)


async def create_attachment(
    db: AsyncSession, user_id: uuid.UUID, filename: str, data: bytes
) -> Attachment:
    parsed = parse_upload(filename, data)
    return await AttachmentRepository(db).create(
        user_id,
        filename=filename,
        kind=parsed.kind,
        content=parsed.text,
        char_count=parsed.char_count,
        token_estimate=parsed.token_estimate,
    )


async def list_for_ids(
    db: AsyncSession, user_id: uuid.UUID, ids: list[str]
) -> list[Attachment]:
    parsed_ids: list[uuid.UUID] = []
    for i in ids:
        try:
            parsed_ids.append(uuid.UUID(i))
        except (ValueError, TypeError):
            continue
    return await AttachmentRepository(db).list_for_user_ids(user_id, parsed_ids)


async def link(
    db: AsyncSession,
    user_id: uuid.UUID,
    ids: list[str],
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> None:
    parsed_ids = [uuid.UUID(i) for i in ids if _is_uuid(i)]
    await AttachmentRepository(db).link(user_id, parsed_ids, conversation_id, message_id)


async def delete_attachment(
    db: AsyncSession, user_id: uuid.UUID, attachment_id: str
) -> bool:
    if not _is_uuid(attachment_id):
        return False
    return await AttachmentRepository(db).delete_for_user(
        uuid.UUID(attachment_id), user_id
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False
