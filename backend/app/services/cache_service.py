"""Semantic response cache (CLAUDE.md § caching).

A tool-free, context-free, non-time-sensitive question is answered once, its
answer stored against the query embedding (`genie.response_cache`), and a later
near-identical question (cosine ≥ ``RESPONSE_CACHE_SIMILARITY``, younger than
``RESPONSE_CACHE_TTL_HOURS``, same user) is served straight from the row —
skipping the whole graph, zero LLM tokens.

Deliberately conservative: only the ``cache_lookup`` graph node calls ``lookup``
and only when the turn used no agents / no KB / no conversation context.
"""

from __future__ import annotations

import re
import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.rag import embedder
from app.config import settings

logger = structlog.get_logger(__name__)

# Words that make an answer perishable — never cache or serve these.
_TIME_WORDS = re.compile(
    r"\b(today|tonight|now|currently|current|latest|recent(?:ly)?|"
    r"yesterday|tomorrow|breaking|upcoming|this (?:week|month|year)|"
    r"news|headline|price|stock|weather|forecast|score|live|"
    r"20\d\d|as of)\b",
    re.I,
)


def normalize(query: str) -> str:
    return " ".join(query.split()).strip()


def is_cacheable_query(query: str | None) -> bool:
    q = normalize(query or "")
    if not (15 <= len(q) <= 2000):
        return False
    return _TIME_WORDS.search(q) is None


async def lookup(db: AsyncSession, user_id: str, query: str) -> dict | None:
    """The best live cache row for ``query`` if it clears the similarity floor."""
    q = normalize(query)
    vec = (await embedder.embed_batch([q]))[0]
    row = (
        await db.execute(
            text(
                """
                SELECT id::text, response, hit_count,
                       EXTRACT(EPOCH FROM (now() - created_at)) AS age_s,
                       1 - (query_embedding <=> CAST(:v AS vector)) AS similarity
                FROM genie.response_cache
                WHERE user_id = :u
                  AND created_at > now() - make_interval(hours => :ttl)
                ORDER BY query_embedding <=> CAST(:v AS vector)
                LIMIT 1
                """
            ),
            {"v": str(vec), "u": user_id, "ttl": settings.RESPONSE_CACHE_TTL_HOURS},
        )
    ).mappings().first()

    if row is None or row["similarity"] < settings.RESPONSE_CACHE_SIMILARITY:
        logger.info(
            "cache_miss",
            best_similarity=round(float(row["similarity"]), 3) if row else None,
        )
        return None

    await db.execute(
        text(
            "UPDATE genie.response_cache SET hit_count = hit_count + 1, "
            "last_hit_at = now() WHERE id = :id"
        ),
        {"id": row["id"]},
    )
    await db.commit()
    logger.info(
        "cache_hit",
        similarity=round(float(row["similarity"]), 3),
        age_s=round(float(row["age_s"])),
        prior_hits=row["hit_count"],
    )
    return {
        "response": row["response"],
        "similarity": float(row["similarity"]),
        "age_s": float(row["age_s"]),
    }


async def store(
    db: AsyncSession, user_id: str, query: str, response: str, model: str | None
) -> None:
    """Cache one answer + prune the user's cache back to the cap."""
    q = normalize(query)
    if not is_cacheable_query(q) or not response.strip():
        return
    vec = (await embedder.embed_batch([q]))[0]
    await db.execute(
        text(
            """
            INSERT INTO genie.response_cache
                (id, user_id, query_norm, query_embedding, response, model, created_at, updated_at)
            VALUES (:id, :u, :q, CAST(:v AS vector), :r, :m, now(), now())
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "u": user_id,
            "q": q,
            "v": str(vec),
            "r": response,
            "m": model,
        },
    )
    await db.execute(
        text(
            """
            DELETE FROM genie.response_cache
            WHERE user_id = :u AND id NOT IN (
                SELECT id FROM genie.response_cache WHERE user_id = :u
                ORDER BY created_at DESC LIMIT :cap
            )
            """
        ),
        {"u": user_id, "cap": settings.RESPONSE_CACHE_MAX_PER_USER},
    )
    await db.commit()
    logger.info("cache_stored", chars=len(response), model=model)


async def sweep(db: AsyncSession) -> int:
    """Delete rows past the TTL. Called hourly from the lifespan."""
    result = await db.execute(
        text(
            "DELETE FROM genie.response_cache "
            "WHERE created_at < now() - make_interval(hours => :ttl)"
        ),
        {"ttl": settings.RESPONSE_CACHE_TTL_HOURS},
    )
    await db.commit()
    n = getattr(result, "rowcount", 0) or 0
    if n:
        logger.info("cache_swept", deleted=n)
    return n
