"""Retrieve owner-scoped candidates using cosine similarity and full-text search."""

from dataclasses import dataclass, replace
from math import isfinite
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.config import Settings
from app.db import Document, DocumentChunk, database_errors
from app.llm_client import EmbeddingClient


@dataclass(frozen=True)
class RetrievedChunk:
    """Carry the source details and ranking scores for a passage."""

    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None
    section: str | None
    position: int
    text: str
    similarity: float
    keyword_rank: int | None = None
    rrf_score: float = 0.0
    citation_id: str = ""
    doc_header: str | None = None


def _owned_chunks(owner_id: str) -> Select:
    return (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            Document.filename,
            Document.doc_header,
            DocumentChunk.page,
            DocumentChunk.section,
            DocumentChunk.position,
            DocumentChunk.text,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.owner_id == owner_id, Document.owner_id == owner_id)
    )


async def _search(session: AsyncSession, statement: Select) -> list[RetrievedChunk]:
    with database_errors():
        rows = (await session.execute(statement)).mappings()
        chunks = []
        for row in rows:
            fields = dict(row)
            distance = fields.pop("distance")
            similarity = round(1.0 - distance, 4) if distance is not None else 0.0
            chunks.append(
                RetrievedChunk(**fields, similarity=similarity if isfinite(similarity) else 0.0)
            )
        return chunks


async def dense_search(
    session: AsyncSession, owner_id: str, query_vector: list[float], limit: int
) -> list[RetrievedChunk]:
    """Return the closest owned chunks by pgvector cosine distance."""

    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    statement = (
        _owned_chunks(owner_id).add_columns(distance.label("distance"))
        .order_by(distance).limit(limit)
    )
    return await _search(session, statement)


async def keyword_search(
    session: AsyncSession,
    owner_id: str,
    question: str,
    limit: int,
    *,
    query_vector: list[float] | None = None,
) -> list[RetrievedChunk]:
    """Rank owned chunks with English full-text search and optional cosine scores."""

    query = func.websearch_to_tsquery(literal_column("'english'"), question)
    rank = func.ts_rank_cd(DocumentChunk.search_tsv, query)
    distance = (
        DocumentChunk.embedding.cosine_distance(query_vector)
        if query_vector is not None else literal_column("NULL")
    )
    statement = (
        _owned_chunks(owner_id).add_columns(distance.label("distance"))
        .where(DocumentChunk.search_tsv.bool_op("@@")(query))
        .order_by(rank.desc(), DocumentChunk.id).limit(limit)
    )
    return [
        replace(chunk, keyword_rank=index)
        for index, chunk in enumerate(await _search(session, statement), 1)
    ]


def reciprocal_rank_fusion(
    dense: list[RetrievedChunk], keyword: list[RetrievedChunk], k: int
) -> list[RetrievedChunk]:
    """Fuse ranked lists, keeping the dense score for shared candidates."""

    fused: dict[UUID, RetrievedChunk] = {}
    for rank, chunk in enumerate(dense, 1):
        fused[chunk.chunk_id] = replace(chunk, rrf_score=1 / (k + rank))
    for rank, chunk in enumerate(keyword, 1):
        existing = fused.get(chunk.chunk_id)
        fused[chunk.chunk_id] = replace(
            existing or chunk,
            keyword_rank=rank,
            rrf_score=(existing.rrf_score if existing else 0.0) + 1 / (k + rank),
        )
    return sorted(fused.values(), key=lambda chunk: chunk.rrf_score, reverse=True)


async def retrieve(
    session: AsyncSession,
    owner_id: str,
    question: str,
    embedder: EmbeddingClient,
    settings: Settings,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Embed a question, rank its candidates, and assign citations to the final hits."""

    (query_vector,) = await embedder.embed([question])
    with database_errors():
        async with session.begin():
            ranked = await dense_search(session, owner_id, query_vector, settings.candidate_k)
            if settings.retrieval_mode == "hybrid":
                keyword = await keyword_search(
                    session, owner_id, question, settings.candidate_k, query_vector=query_vector
                )
                ranked = reciprocal_rank_fusion(ranked, keyword, settings.rrf_k)
    limit = settings.top_k if top_k is None else top_k
    return [
        replace(chunk, citation_id=f"C{index}")
        for index, chunk in enumerate(ranked[:limit], 1)
    ]


async def count_owner_documents(session: AsyncSession, owner_id: str) -> int:
    """Count ingested documents owned by the caller."""

    with database_errors():
        async with session.begin():
            count = await session.scalar(
                select(func.count()).select_from(Document).where(Document.owner_id == owner_id)
            )
    return count or 0
