"""Embeddings — OpenAI ``text-embedding-3-small`` (1536-d).

Always OpenAI regardless of ``LLM_PROVIDER`` (CLAUDE.md §3). Used by the ingestion
worker (store) and, later, retrieval (query embedding).
"""

from __future__ import annotations

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_BATCH = 96  # OpenAI accepts up to 2048 inputs; keep batches modest


def _model():
    from langchain_openai import OpenAIEmbeddings

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings")
    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBEDDING_MODEL, api_key=settings.OPENAI_API_KEY
    )


async def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _model()
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH):
        batch = texts[i : i + _BATCH]
        out.extend(await model.aembed_documents(batch))
    logger.info(
        "embeddings_done",
        model=settings.OPENAI_EMBEDDING_MODEL,
        count=len(texts),
        total_chars=sum(len(t) for t in texts),
    )
    return out


async def embed_text(text: str) -> list[float]:
    return (await embed_batch([text]))[0]
