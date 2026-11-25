"""Exercise document ingestion against PostgreSQL with deterministic embeddings."""

import hashlib
import random
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete

from app.config import get_settings
from app.db import Document, SessionFactory
from app.llm_client import get_embedding_client
from app.main import app, get_owner_id
from app.repository import count_chunks


class FakeEmbeddingClient:
    """Return a reproducible vector for each input without contacting Ollama."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Build deterministic vectors of the configured dimension."""

        vectors = []
        for text in texts:
            random_generator = random.Random(hashlib.sha256(text.encode()).digest())
            vectors.append(
                [random_generator.random() for _ in range(get_settings().embed_dimensions)]
            )
        return vectors

    async def check_health(self) -> bool:
        """Report a healthy fake embedding service."""

        return True


@pytest.fixture
async def document_api() -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    """Start the app and isolate each test by a unique owner that is cleaned up."""

    owner_id = f"test-{uuid4()}"
    app.dependency_overrides[get_owner_id] = lambda: owner_id
    app.dependency_overrides[get_embedding_client] = FakeEmbeddingClient
    try:
        async with app.router.lifespan_context(app):
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://testserver"
                ) as client:
                    yield client, owner_id
            finally:
                async with SessionFactory.begin() as session:
                    await session.execute(delete(Document).where(Document.owner_id == owner_id))
    finally:
        app.dependency_overrides.pop(get_owner_id, None)
        app.dependency_overrides.pop(get_embedding_client, None)


async def _upload(client: httpx.AsyncClient, path: Path) -> httpx.Response:
    return await client.post("/documents", files={"file": (path.name, path.read_bytes())})


def _assert_error(response: httpx.Response, status_code: int, code: str) -> dict[str, str]:
    assert response.status_code == status_code, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert response.headers["X-Request-ID"] == error["request_id"]
    assert error["request_id"]
    return error


async def test_upload_document(
    document_api: tuple[httpx.AsyncClient, str], corpus_dir: Path
) -> None:
    """Store the remote work policy and expose its metadata."""

    client, _ = document_api
    response = await _upload(client, corpus_dir / "remote_work_policy.docx")
    assert response.status_code == 201, response.text
    document = response.json()
    assert UUID(document["id"])
    assert document["filename"] == "remote_work_policy.docx"
    assert document["file_type"] == "docx"
    assert document["num_chunks"] > 0


async def test_upload_duplicate(
    document_api: tuple[httpx.AsyncClient, str], corpus_dir: Path
) -> None:
    """Reject a repeated upload and identify the originally stored document."""

    client, _ = document_api
    path = corpus_dir / "remote_work_policy.docx"
    first = await _upload(client, path)
    assert first.status_code == 201, first.text
    error = _assert_error(await _upload(client, path), 409, "duplicate_document")
    assert first.json()["id"] in error["message"]


@pytest.mark.parametrize(
    ("filename", "content", "status_code", "code"),
    [
        ("notes.xlsx", b"Spreadsheet", 415, "unsupported_file_type"),
        ("blank.txt", b"", 400, "empty_file"),
        ("fake.pdf", b"these are not PDF bytes", 400, "corrupt_file"),
    ],
)
async def test_invalid_uploads(
    document_api: tuple[httpx.AsyncClient, str],
    filename: str,
    content: bytes,
    status_code: int,
    code: str,
) -> None:
    """Return consistent errors for upload metadata and signature failures."""

    client, _ = document_api
    response = await client.post("/documents", files={"file": (filename, content)})
    _assert_error(response, status_code, code)


async def test_reject_scanned_document(
    document_api: tuple[httpx.AsyncClient, str], corpus_dir: Path
) -> None:
    """Reject a valid PDF that has no extractable text."""

    client, _ = document_api
    response = await _upload(client, corpus_dir / "scanned_office_notice.pdf")
    _assert_error(response, 400, "no_extractable_text")


async def test_list_documents(
    document_api: tuple[httpx.AsyncClient, str], corpus_dir: Path
) -> None:
    """List only the document uploaded for this test's owner."""

    client, _ = document_api
    uploaded = await _upload(client, corpus_dir / "remote_work_policy.docx")
    assert uploaded.status_code == 201, uploaded.text
    listed = await client.get("/documents")
    assert listed.status_code == 200
    assert listed.json() == {"documents": [uploaded.json()], "total": 1}


async def test_delete_document_and_chunks(
    document_api: tuple[httpx.AsyncClient, str], corpus_dir: Path
) -> None:
    """Confirm deletion removes the owned document and all of its chunks."""

    client, owner_id = document_api
    uploaded = await _upload(client, corpus_dir / "remote_work_policy.docx")
    assert uploaded.status_code == 201, uploaded.text
    document_id = UUID(uploaded.json()["id"])
    route = f"/documents/{document_id}"
    retrieved = await client.get(route)
    assert retrieved.status_code == 200
    assert retrieved.json() == uploaded.json()
    async with SessionFactory() as session:
        assert await count_chunks(session, document_id, owner_id=owner_id) > 0

    removed = await client.delete(route)
    assert removed.status_code == 204
    assert removed.content == b""
    _assert_error(await client.get(route), 404, "document_not_found")
    async with SessionFactory() as session:
        assert await count_chunks(session, document_id, owner_id=owner_id) == 0


async def test_delete_unknown_document(document_api: tuple[httpx.AsyncClient, str]) -> None:
    """Return a document-not-found error when the ID does not exist."""

    client, _ = document_api
    _assert_error(await client.delete(f"/documents/{uuid4()}"), 404, "document_not_found")


async def test_invalid_document_id(document_api: tuple[httpx.AsyncClient, str]) -> None:
    """Return the validation envelope with the caller's request ID."""

    client, _ = document_api
    response = await client.get(
        "/documents/not-a-uuid", headers={"X-Request-ID": "test-invalid-document-id"}
    )
    error = _assert_error(response, 422, "validation_error")
    assert error["request_id"] == "test-invalid-document-id"
