"""Orchestrate validation, extraction, chunking, embedding, and storage."""

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import islice
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import Document, database_errors
from app.errors import DuplicateDocumentError
from app.ingestion.chunking import chunk_document
from app.ingestion.extractors import ExtractedDocument, extract_document
from app.ingestion.validation import compute_sha256, sanitize_filename, validate_upload
from app.llm_client import EmbeddingClient
from app.repository import create_document_with_chunks, get_document_by_hash

logger = logging.getLogger(__name__)
_MAX_DOCUMENT_HEADER_CHARS = 200


def _document_header(document: ExtractedDocument) -> str | None:
    nonempty_lines = (
        line
        for section in document.sections
        for raw_line in section.text.splitlines()
        if (line := raw_line.strip())
    )
    return "\n".join(islice(nonempty_lines, 2))[:_MAX_DOCUMENT_HEADER_CHARS] or None


@contextmanager
def _timed_step(name: str) -> Iterator[None]:
    start = perf_counter()
    try:
        yield
    finally:
        logger.info("Ingestion %s took %.1f ms", name, (perf_counter() - start) * 1000)


async def ingest_document(
    data: bytes,
    filename: str,
    owner_id: str,
    session: AsyncSession,
    embedder: EmbeddingClient,
    settings: Settings,
) -> Document:
    """Validate, extract, chunk, embed, and persist a document for its owner."""

    with _timed_step("sanitize_filename"):
        filename = sanitize_filename(filename)
    with _timed_step("validate_upload"):
        extension = validate_upload(filename, data, settings)
    with _timed_step("sha256"):
        sha256 = compute_sha256(data)
    with _timed_step("duplicate_check"), database_errors():
        # Release the database connection before extraction and embedding.
        async with session.begin():
            existing = await get_document_by_hash(session, owner_id, sha256)
            if existing is not None:
                raise DuplicateDocumentError(existing.id)
    with _timed_step("extract_document"):
        extracted = await asyncio.to_thread(extract_document, data, filename)
        doc_header = _document_header(extracted)
    with _timed_step("chunk_document"):
        chunks = chunk_document(extracted, settings)
    with _timed_step("embed"):
        embeddings = await embedder.embed([chunk.embed_text for chunk in chunks])
    with _timed_step("create_document_with_chunks"):
        return await create_document_with_chunks(
            session,
            owner_id=owner_id,
            filename=filename,
            file_type=extension.lstrip("."),
            sha256=sha256,
            size_bytes=len(data),
            warnings=extracted.warnings,
            chunks=chunks,
            embeddings=embeddings,
            doc_header=doc_header,
        )
