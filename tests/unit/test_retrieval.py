"""Check fusion scores and citation numbering without provider requests."""

from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID

import pytest

from app import retrieval
from app.config import get_settings
from app.retrieval import RetrievedChunk, reciprocal_rank_fusion


def _chunk(number: int, similarity: float) -> RetrievedChunk:
    return RetrievedChunk(
        UUID(int=number), UUID(int=100), "policy.pdf", 1, "Leave", number,
        "Annual leave", similarity,
    )


def test_reciprocal_rank_fusion() -> None:
    """Score each ranking from one and keep dense and keyword-only similarities."""

    first, shared, keyword_only = _chunk(1, 0.8), _chunk(2, 0.7), _chunk(3, 0.6)
    fused = reciprocal_rank_fusion(
        [first, shared], [replace(shared, similarity=0.1), keyword_only], 60
    )
    assert [item.chunk_id for item in fused] == [shared.chunk_id, first.chunk_id, keyword_only.chunk_id]
    assert [item.rrf_score for item in fused] == pytest.approx([1 / 61 + 1 / 62, 1 / 61, 1 / 62])
    assert [item.similarity for item in fused] == [0.7, 0.8, 0.6]
    assert [item.keyword_rank for item in fused] == [1, None, 2]


async def test_retrieval_assigns_ordered_citation_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assign citation IDs after fusion and top-k truncation."""

    first, shared, keyword_only = _chunk(1, 0.8), _chunk(2, 0.7), _chunk(3, 0.6)

    async def dense(*args: object) -> list[RetrievedChunk]:
        return [first, shared]

    async def keyword(*args: object, query_vector: list[float]) -> list[RetrievedChunk]:
        assert query_vector == [1.0]
        return [shared, keyword_only]

    class Session:
        @asynccontextmanager
        async def begin(self):
            yield

    class Embedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            assert texts == ["How much leave?"]
            return [[1.0]]

    monkeypatch.setattr(retrieval, "dense_search", dense)
    monkeypatch.setattr(retrieval, "keyword_search", keyword)
    settings = get_settings().model_copy(update={"retrieval_mode": "hybrid"})
    chunks = await retrieval.retrieve(Session(), "test", "How much leave?", Embedder(), settings, 2)
    assert [(item.citation_id, item.chunk_id) for item in chunks] == [
        ("C1", shared.chunk_id), ("C2", first.chunk_id)
    ]
