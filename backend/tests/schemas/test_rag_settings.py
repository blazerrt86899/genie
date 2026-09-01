"""RagSettings — defaults, clamping, enum (CLAUDE.md §10)."""

from __future__ import annotations

import pytest
from app.schemas.rag import RagSettings, SearchStrategy, resolve
from pydantic import ValidationError


def test_resolve_empty_gives_defaults():
    s = resolve({})
    assert s.embedding_model == "text-embedding-3-small"
    assert s.search_strategy is SearchStrategy.hybrid
    assert s.chunks_per_search == 10
    assert s.final_context_size == 5


def test_resolve_none_gives_defaults():
    assert resolve(None).num_queries == 5


def test_partial_override_merges():
    s = resolve({"search_strategy": "vector", "chunks_per_search": 20})
    assert s.search_strategy is SearchStrategy.vector
    assert s.chunks_per_search == 20
    assert s.similarity_threshold == 0.3  # untouched default


def test_out_of_bounds_rejected():
    with pytest.raises(ValidationError):
        RagSettings(chunks_per_search=99)
    with pytest.raises(ValidationError):
        RagSettings(similarity_threshold=2.0)


def test_unknown_keys_ignored():
    s = RagSettings(**{"search_strategy": "hybrid", "bogus": 1})
    assert s.search_strategy is SearchStrategy.hybrid
