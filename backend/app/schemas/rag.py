"""Per-project Knowledge-Base retrieval config (CLAUDE.md §10).

Stored as ``projects.rag_settings`` JSONB; ``resolve()`` fills defaults.
``embedding_model`` is locked once the project has any document (changing it
would invalidate every stored vector).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# Only text-embedding-3-small (1536-d) is wired today — the dropdown exists for
# forward-compat and the "locked after first upload" rule.
EMBEDDING_MODELS: tuple[str, ...] = ("text-embedding-3-small",)


class SearchStrategy(StrEnum):
    vector = "vector"  # semantic similarity only
    hybrid = "hybrid"  # semantic + keyword (RRF)
    multi_query_vector = "multi_query_vector"  # N paraphrases → vector each → fuse
    multi_query_hybrid = "multi_query_hybrid"  # N paraphrases → hybrid each → fuse


class RagSettings(BaseModel):
    model_config = {"extra": "ignore"}

    embedding_model: str = "text-embedding-3-small"
    search_strategy: SearchStrategy = SearchStrategy.hybrid
    chunks_per_search: int = Field(default=10, ge=5, le=30)
    final_context_size: int = Field(default=5, ge=3, le=10)
    # `text-embedding-3-small` cosine scores run low — a relevant hit is often
    # ~0.25-0.5. Keep this a gentle floor, not a hard gate (retrieval always
    # keeps its best hit). 0 = no filter.
    similarity_threshold: float = Field(default=0.15, ge=0.0, le=0.9)
    num_queries: int = Field(default=5, ge=2, le=10)
    chunk_size: int = Field(default=1200, ge=400, le=4000)  # characters
    chunk_overlap: int = Field(default=150, ge=0, le=600)


def resolve(raw: dict | None) -> RagSettings:
    return RagSettings(**(raw or {}))
