"""Define the async database connection and vector-backed document models."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import PUBLIC_OWNER_ID, get_settings
from app.errors import ExternalServiceError

logger = logging.getLogger(__name__)
_settings = get_settings()
DOCUMENT_HASH_CONSTRAINT = "uq_documents_owner_sha256"

engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    hide_parameters=True,
    pool_timeout=_settings.database_timeout_seconds,
    connect_args={
        "timeout": _settings.database_timeout_seconds,
        "command_timeout": _settings.database_timeout_seconds,
    },
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Provide shared SQLAlchemy model metadata."""


class User(Base):
    """Store a user's normalized email and bcrypt credential."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    """Store file metadata and ownership for an ingested document."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("owner_id", "sha256", name=DOCUMENT_HASH_CONSTRAINT),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(
        String(64), default=PUBLIC_OWNER_ID, server_default=PUBLIC_OWNER_ID
    )
    filename: Mapped[str] = mapped_column(String(255))
    doc_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(10))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    num_chunks: Mapped[int]
    warnings: Mapped[list[str]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentChunk(Base):
    """Store source text, retrieval metadata, and an embedding."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_search_tsv_gin", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int]
    page: Mapped[int | None]
    section: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(_settings.embed_dimensions))
    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
    document: Mapped[Document] = relationship(back_populates="chunks")


class AskLog(Base):
    """Store question-answering telemetry without the question or answer text."""

    __tablename__ = "ask_logs"
    __table_args__ = (Index("ix_ask_logs_owner_created_at", "owner_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(128))
    question_chars: Mapped[int]
    latency_ms: Mapped[float]
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(255))
    refused: Mapped[bool]
    refusal_reason: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[bool]
    prompt_tokens: Mapped[int]
    completion_tokens: Mapped[int]
    retrieved_count: Mapped[int]
    timings_ms: Mapped[dict[str, float]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


@contextmanager
def database_errors() -> Iterator[None]:
    """Translate database and connection failures without exposing SQL or values."""

    try:
        yield
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        logger.warning("Database operation failed (%s)", type(exc).__name__)
        raise ExternalServiceError("Database service unavailable") from None


async def init_db() -> None:
    """Enable pgvector and create the application tables at startup."""

    with database_errors():
        async with engine.begin() as connection:
            await connection.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Alembic migrations are outside this project's scope. Create tables at startup.
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                sql_text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_header TEXT")
            )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async database session."""

    async with SessionFactory() as session:
        yield session
