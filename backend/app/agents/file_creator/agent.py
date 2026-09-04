"""File Creator agent (CLAUDE.md §12).

Single responsibility: turn this turn's content (the request itself, plus any
earlier steps it `depends_on` — e.g. a `web_search` step's findings) into a
real, downloadable file — Markdown, text, CSV, JSON, code, or a Word/PDF/Excel
document — and store it. Never searches the web or manages tasks itself; a
request that needs research first gets that as a separate step this one
depends on (the supervisor's job).
"""

from __future__ import annotations

import re
import uuid

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import AgentResult
from app.agents.file_creator.prompts import FILE_CONTENT_PROMPT, FILE_SPEC_PROMPT
from app.agents.file_creator.schemas import FileSpec
from app.agents.models import ainvoke, get_chat_model, get_utility_model
from app.agents.supervisor.state import GenieState, TaskRecord
from app.db.session import get_sessionmaker
from app.services import file_service

logger = structlog.get_logger(__name__)

_EXT: dict[str, str] = {
    "md": "md", "txt": "txt", "csv": "csv", "json": "json",
    "docx": "docx", "pdf": "pdf", "xlsx": "xlsx",
}


def _safe_filename(name: str, fmt: str, code_ext: str | None) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", (name or "").strip()) or "document"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "document"
    ext = (code_ext or "txt").lstrip(".") if fmt == "code" else _EXT.get(fmt, "txt")
    return f"{stem}.{ext}"


def _gather_context(state: GenieState, task: TaskRecord) -> str:
    parts = [f"The user's request for this file: {task.get('description', '')}"]
    results = state.get("intermediate_results") or {}
    for dep_id in task.get("depends_on") or []:
        r = results.get(dep_id)
        if r and r.get("summary"):
            parts.append(f"Findings from {r.get('agent', 'a prior step')}:\n{r['summary']}")
    if len(parts) == 1:  # no dependency findings — fall back to the raw conversation
        for msg in reversed(state.get("messages") or []):
            if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
                parts.append(f"The user's latest message: {msg.content}")
                break
    return "\n\n".join(parts)


def _summarize(content: str) -> str:
    heading = next(
        (line.lstrip("#").strip() for line in content.splitlines() if line.strip().startswith("#")),
        None,
    )
    if heading:
        return heading
    text = " ".join(content.split())
    return text[:140] + ("…" if len(text) > 140 else "")


async def run_file_creator(state: GenieState, task: TaskRecord) -> AgentResult:
    context = _gather_context(state, task)

    spec: FileSpec | None = None
    try:
        spec_model = get_utility_model(temperature=0).with_structured_output(
            FileSpec, include_raw=True
        )
        spec_request = task.get("description") or context
        result = await ainvoke(
            spec_model,
            [HumanMessage(content=FILE_SPEC_PROMPT.format(request=spec_request))],
        )
        spec = result["parsed"]
    except Exception:  # noqa: BLE001
        logger.warning("file_creator_spec_failed", exc_info=True)
    if spec is None:
        spec = FileSpec(filename="document", format="md")

    filename = _safe_filename(spec.filename, spec.format, spec.code_ext)
    mime = file_service.mime_for(spec.format, spec.code_ext)
    logger.info("file_creator_spec", task_id=task.get("id"), filename=filename, format=spec.format)

    content_model = get_chat_model(model_id=state.get("model"), streaming=False, temperature=0.4)
    prompt = FILE_CONTENT_PROMPT.format(format=spec.format, filename=filename, context=context)
    resp = await ainvoke(content_model, [SystemMessage(content=prompt)])
    body = str(resp.content).strip()
    if not body:
        raise RuntimeError("file_creator produced no content")

    data = file_service.render(spec.format, body)
    summary = _summarize(body)

    async with get_sessionmaker()() as db:
        row = await file_service.upload(
            db,
            uuid.UUID(state["user_id"]),
            uuid.UUID(state["conversation_id"]),
            filename=filename,
            fmt=spec.format,
            data=data,
            mime_type=mime,
            summary=summary,
        )

    logger.info(
        "file_creator_done",
        task_id=task.get("id"),
        file_id=str(row.id),
        format=spec.format,
        bytes=len(data),
    )
    return AgentResult(
        summary=f"Created {filename} — {summary}",
        detail=body[:2000],
        files=[
            {
                "id": str(row.id),
                "filename": row.filename,
                "mime_type": row.mime_type,
                "byte_size": row.byte_size,
                "summary": row.summary,
            }
        ],
    )
