"""Provide a shared async Ollama client for embedding and health checks."""

from math import isfinite
from typing import cast

import httpx
from starlette.requests import Request
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import Settings
from app.errors import ExternalServiceError


class EmbeddingClient:
    """Embed batches over a shared HTTP connection pool."""

    def __init__(self, settings: Settings) -> None:
        """Configure the Ollama endpoint and request timeout."""

        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=settings.http_timeout_seconds
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings in input order, retrying transient request failures."""

        vectors: list[list[float]] = []
        batch_size = self._settings.embedding_batch_size
        try:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                response = await self._request_embeddings(batch)
                vectors.extend(self._validate_vectors(response.json(), len(batch)))
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, OverflowError) as exc:
            raise ExternalServiceError("Embedding service unavailable") from exc
        return vectors

    async def check_health(self) -> bool:
        """Check whether Ollama responds successfully to its tags endpoint."""

        try:
            response = await self._client.get("/api/tags")
            return response.is_success
        except (httpx.HTTPError, httpx.InvalidURL):
            return False

    async def aclose(self) -> None:
        """Close the shared HTTP client."""

        await self._client.aclose()

    async def _request_embeddings(self, batch: list[str]) -> httpx.Response:
        retry = AsyncRetrying(
            stop=stop_after_attempt(self._settings.http_max_retries),
            wait=wait_exponential(),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )
        return await retry(self._post_batch, batch)

    async def _post_batch(self, batch: list[str]) -> httpx.Response:
        response = await self._client.post(
            "/api/embed", json={"model": self._settings.embed_model, "input": batch}
        )
        return response.raise_for_status()

    def _validate_vectors(self, payload: object, expected_count: int) -> list[list[float]]:
        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != expected_count:
            raise ValueError("Unexpected embedding count")
        for vector in vectors:
            if (
                not isinstance(vector, list)
                or len(vector) != self._settings.embed_dimensions
                or any(type(value) not in (float, int) or not isfinite(value) for value in vector)
            ):
                raise ValueError("Invalid embedding vector")
        return [[float(value) for value in vector] for vector in vectors]


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, httpx.TransportError) or (
        isinstance(exc, httpx.HTTPStatusError) and 500 <= exc.response.status_code < 600
    )


def get_embedding_client(request: Request) -> EmbeddingClient:
    """Return the client created for the current application lifespan."""

    return cast(EmbeddingClient, request.app.state.embedding_client)


# TODO: Add chat and LLM methods when answer generation is implemented.
