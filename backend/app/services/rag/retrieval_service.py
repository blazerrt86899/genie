"""Project Knowledge-Base retrieval (CLAUDE.md §10) — commit 2.

Not a registry agent: the `retriever` graph node calls this with the project's
``RagSettings``. Strategies:
  vector             — pgvector cosine top-k
  hybrid             — genie.hybrid_search_project_chunks RPC (RRF: semantic + FTS)
  multi_query_*      — utility model writes N paraphrases → run the base strategy
                       per query → RRF-fuse → top ``final_context_size``
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag import embedder
from app.schemas.rag import RagSettings, SearchStrategy

logger = structlog.get_logger(__name__)


_MIN_KEEP = 3  # text-embedding-3-small scores run low; don't let the floor starve retrieval


def _soft_threshold(rows: list[dict], threshold: float) -> list[dict]:
    """Trim the tail below ``threshold``, but always keep the strongest few — a
    good chunk for this model often scores ~0.25-0.4, and retrieval degrading to
    nothing is worse than a weak hit. The synthesiser is told to say so if the
    passages don't actually answer the question (rows are already rank-ordered)."""
    if not rows:
        return []
    kept = [r for r in rows if (r.get("similarity") or 0.0) >= threshold]
    return kept if len(kept) >= _MIN_KEEP else rows[: max(_MIN_KEEP, len(kept))]


async def _fetch_filenames(db: AsyncSession, project_id: uuid.UUID) -> dict[str, str]:
    rows = (
        await db.execute(
            text("SELECT id::text, filename FROM genie.documents WHERE project_id = :p"),
            {"p": str(project_id)},
        )
    ).all()
    return {r[0]: r[1] for r in rows}


async def _vector(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, qvec: list[float], s: RagSettings
) -> list[dict]:
    rows = (
        await db.execute(
            text(
                """
                SELECT id::text, content, metadata, document_id::text,
                       1 - (embedding <=> CAST(:q AS vector)) AS similarity
                FROM genie.document_chunks
                WHERE project_id = :p AND user_id = :u
                ORDER BY embedding <=> CAST(:q AS vector)
                LIMIT :k
                """
            ),
            {"q": str(qvec), "p": str(project_id), "u": str(user_id), "k": s.chunks_per_search},
        )
    ).mappings().all()
    return _soft_threshold(
        [dict(r) | {"score": r["similarity"]} for r in rows], s.similarity_threshold
    )


async def _hybrid(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    qvec: list[float],
    s: RagSettings,
) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT id::text, content, metadata, document_id::text, similarity, score "
                "FROM genie.hybrid_search_project_chunks("
                ":qt, CAST(:qe AS vector), :p, :u, :k, :thr)"
            ),
            {
                "qt": query,
                "qe": str(qvec),
                "p": str(project_id),
                "u": str(user_id),
                "k": s.chunks_per_search,
                "thr": 0.0,  # soft-threshold in Python instead — see _soft_threshold
            },
        )
    ).mappings().all()
    return _soft_threshold([dict(r) for r in rows], s.similarity_threshold)


def _rrf_fuse(result_lists: list[list[dict]], k: int = 50) -> list[dict]:
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for lst in result_lists:
        for rank, row in enumerate(lst, start=1):
            cid = row["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            by_id.setdefault(cid, row)
    return [by_id[cid] for cid, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)]


async def _paraphrases(query: str, n: int) -> list[str]:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.models import ainvoke, get_utility_model

    try:
        resp = await ainvoke(
            get_utility_model(temperature=0.5, max_tokens=200),
            [
                SystemMessage(
                    content=f"Rewrite the question {n} different ways to widen a document "
                    "search — vary wording and angle, keep the meaning. One per line, no numbering."
                ),
                HumanMessage(content=query),
            ],
        )
        lines = [ln.strip("-• ").strip() for ln in str(resp.content).splitlines() if ln.strip()]
        return ([query] + lines)[:n]
    except Exception:  # noqa: BLE001
        logger.warning("rag_paraphrase_failed", exc_info=True)
        return [query]


async def retrieve(
    db: AsyncSession,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    settings: RagSettings,
) -> list[dict]:
    """Return the top ``final_context_size`` chunks for the query, per strategy."""
    queries = [query]
    if settings.search_strategy in (
        SearchStrategy.multi_query_vector,
        SearchStrategy.multi_query_hybrid,
    ):
        queries = await _paraphrases(query, settings.num_queries)

    qvecs = await embedder.embed_batch(queries)
    base_hybrid = settings.search_strategy in (
        SearchStrategy.hybrid,
        SearchStrategy.multi_query_hybrid,
    )

    per_query: list[list[dict]] = []
    for q, v in zip(queries, qvecs, strict=True):
        if base_hybrid:
            per_query.append(await _hybrid(db, project_id, user_id, q, v, settings))
        else:
            per_query.append(await _vector(db, project_id, user_id, v, settings))

    fused = per_query[0] if len(per_query) == 1 else _rrf_fuse(per_query)
    top = fused[: settings.final_context_size]

    names = await _fetch_filenames(db, project_id)
    out = [
        {
            "content": r["content"],
            "similarity": round(float(r.get("similarity") or 0.0), 3),
            "heading": (r.get("metadata") or {}).get("heading"),
            "filename": names.get(r["document_id"], "document"),
        }
        for r in top
    ]
    logger.info(
        "rag_retrieved",
        strategy=settings.search_strategy,
        queries=len(queries),
        chunks=len(out),
    )
    return out
