"""Provide database access functions for documents and chunks."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PUBLIC_OWNER_ID
from app.db import DOCUMENT_HASH_CONSTRAINT, Document, DocumentChunk, database_errors
from app.errors import DocumentNotFoundError, DuplicateDocumentError, ExternalServiceError
from app.ingestion.chunking import Chunk


async def get_document_by_hash(
    session: AsyncSession, owner_id: str, sha256: str
) -> Document | None:
    """Find an uploaded file by digest within one owner's documents."""

    with database_errors():
        return await session.scalar(
            select(Document).where(Document.owner_id == owner_id, Document.sha256 == sha256)
        )


async def create_document_with_chunks(
    session: AsyncSession,
    *,
    owner_id: str,
    filename: str,
    file_type: str,
    sha256: str,
    size_bytes: int,
    warnings: list[str],
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> Document:
    """Commit a document and its chunks atomically, detecting concurrent duplicates."""

    with database_errors():
        async with session.begin():
            statement = (
                insert(Document)
                .values(
                    owner_id=owner_id,
                    filename=filename,
                    file_type=file_type,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    num_chunks=len(chunks),
                    warnings=warnings,
                )
                .on_conflict_do_nothing(constraint=DOCUMENT_HASH_CONSTRAINT)
                .returning(Document)
            )
            document = await session.scalar(statement)
            if document is None:
                existing = await get_document_by_hash(session, owner_id, sha256)
                if existing is not None:
                    raise DuplicateDocumentError(existing.id)
                raise ExternalServiceError("The document changed during upload. Please retry.")

            session.add_all(
                DocumentChunk(
                    document_id=document.id,
                    owner_id=owner_id,
                    position=chunk.position,
                    page=chunk.page,
                    section=chunk.section,
                    text=chunk.text,
                    word_count=chunk.word_count,
                    embedding=embedding,
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            )
    return document


async def list_documents(session: AsyncSession, owner_id: str) -> list[Document]:
    """List one owner's documents, newest first."""

    with database_errors():
        documents = await session.scalars(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
        return list(documents)


async def get_document(
    session: AsyncSession, owner_id: str, document_id: UUID
) -> Document:
    """Fetch an owned document or raise the same error as for a missing ID."""

    with database_errors():
        document = await session.scalar(
            select(Document).where(Document.owner_id == owner_id, Document.id == document_id)
        )
    if document is None:
        raise DocumentNotFoundError("Document not found.")
    return document


async def delete_document(
    session: AsyncSession, owner_id: str, document_id: UUID
) -> None:
    """Delete an owned document and let PostgreSQL cascade to its chunks."""

    with database_errors():
        async with session.begin():
            deleted_id = await session.scalar(
                delete(Document)
                .where(Document.owner_id == owner_id, Document.id == document_id)
                .returning(Document.id)
            )
            if deleted_id is None:
                raise DocumentNotFoundError("Document not found.")


async def count_chunks(
    session: AsyncSession, document_id: UUID, *, owner_id: str = PUBLIC_OWNER_ID
) -> int:
    """Count stored chunks for an owner and document ID."""

    with database_errors():
        total = await session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.owner_id == owner_id, DocumentChunk.document_id == document_id
            )
        )
    return total or 0
