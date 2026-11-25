"""Check readiness of dependencies used by document ingestion."""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import database_errors
from app.errors import ExternalServiceError
from app.llm_client import EmbeddingClient
from app.schemas import HealthOut


async def check_health(session: AsyncSession, embedder: EmbeddingClient) -> HealthOut:
    """Check PostgreSQL and Ollama concurrently and report their status."""

    database_ok, embedding_ok = await asyncio.gather(
        _check_database(session), embedder.check_health()
    )
    return HealthOut(
        status="ok" if database_ok and embedding_ok else "unavailable",
        database="ok" if database_ok else "unavailable",
        embedding_service="ok" if embedding_ok else "unavailable",
    )


async def _check_database(session: AsyncSession) -> bool:
    try:
        with database_errors():
            return await session.scalar(text("SELECT 1")) == 1
    except ExternalServiceError:
        return False
