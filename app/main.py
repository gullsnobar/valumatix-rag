"""Define the FastAPI application and routes without business logic."""

import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import PUBLIC_OWNER_ID, Settings, get_settings
from app.db import engine, get_session, init_db
from app.errors import RagServiceError
from app.health import check_health
from app.ingestion.pipeline import ingest_document
from app.llm_client import EmbeddingClient, get_embedding_client
from app.logging_config import RequestIdMiddleware, configure_logging
from app.repository import delete_document, get_document, list_documents
from app.schemas import DocumentListOut, DocumentOut, ErrorBody, ErrorResponse, HealthOut

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize and close the shared database engine and Ollama client."""

    configure_logging()
    try:
        await init_db()
        client = EmbeddingClient(get_settings())
        application.state.embedding_client = client
        try:
            yield
        finally:
            await client.aclose()
    finally:
        await engine.dispose()


app = FastAPI(
    title="Tarnwick RAG Service",
    version="0.1.0",
    description="Ingest, list, retrieve, and delete documents for Tarnwick Consulting.",
    lifespan=lifespan,
)


def _error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    body = ErrorResponse(error=ErrorBody(code=code, message=message, request_id=request_id))
    return JSONResponse(
        body.model_dump(mode="json"),
        status_code=status_code,
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RagServiceError)
async def service_error(request: Request, exc: RagServiceError) -> JSONResponse:
    """Convert a known service error to its documented HTTP response."""

    return _error_response(request, exc.status_code, exc.error_code, str(exc))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Respond with a stable validation error without echoing invalid inputs."""

    return _error_response(request, 422, "validation_error", "Request validation failed.")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Use the error envelope for HTTP errors raised by the framework."""

    message = HTTPStatus(exc.status_code).phrase
    response = _error_response(request, exc.status_code, "http_error", message)
    if exc.headers is not None:
        response.headers.update(exc.headers)
    return response


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 and record stack frames without exception payloads."""

    frames = "".join(traceback.format_tb(exc.__traceback__))
    logger.error("Unhandled %s\n%s", type(exc).__name__, frames)
    return _error_response(request, 500, "internal_error", "An unexpected error occurred.")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().cors_allowed_origin],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware, on_error=unexpected_error)


async def get_owner_id() -> str:
    """Provide the public owner until JWT authentication is added."""

    return PUBLIC_OWNER_ID


Owner = Annotated[str, Depends(get_owner_id)]
Session = Annotated[AsyncSession, Depends(get_session)]
Embedder = Annotated[EmbeddingClient, Depends(get_embedding_client)]
ServiceSettings = Annotated[Settings, Depends(get_settings)]

_DOCUMENT_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "A required dependency is unavailable."},
    500: {"model": ErrorResponse, "description": "An unexpected error occurred."},
}
_NOT_FOUND = {"model": ErrorResponse, "description": "The document was not found."}


@app.post(
    "/documents",
    tags=["documents"],
    status_code=201,
    summary="Upload a document",
    description="Extract, chunk, and embed a supported file, then store it for the current owner.",
    responses={
        **_DOCUMENT_RESPONSES,
        400: {"model": ErrorResponse, "description": "Empty, corrupt, or textless file."},
        409: {"model": ErrorResponse, "description": "The owner already uploaded this file."},
        413: {"model": ErrorResponse, "description": "The upload exceeds the size limit."},
        415: {"model": ErrorResponse, "description": "The file extension is unsupported."},
    },
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF, DOCX, PPTX, Markdown, or text file.")],
    owner_id: Owner,
    session: Session,
    embedder: Embedder,
    settings: ServiceSettings,
) -> DocumentOut:
    """Read a bounded multipart upload and pass it to the ingestion pipeline."""

    data = await file.read(settings.max_upload_bytes + 1)
    document = await ingest_document(data, file.filename or "", owner_id, session, embedder, settings)
    return DocumentOut.model_validate(document)


@app.get(
    "/documents",
    tags=["documents"],
    summary="List documents",
    description="Return the current owner's documents, newest first.",
    responses=_DOCUMENT_RESPONSES,
)
async def browse_documents(owner_id: Owner, session: Session) -> DocumentListOut:
    """Return metadata for the owner's documents."""

    documents = await list_documents(session, owner_id)
    return DocumentListOut(
        documents=[DocumentOut.model_validate(document) for document in documents],
        total=len(documents),
    )


@app.get(
    "/documents/{document_id}",
    tags=["documents"],
    summary="Get document metadata",
    description="Return metadata for one document owned by the current caller.",
    responses={**_DOCUMENT_RESPONSES, 404: _NOT_FOUND},
)
async def read_document(document_id: UUID, owner_id: Owner, session: Session) -> DocumentOut:
    """Return one owned document's metadata."""

    return DocumentOut.model_validate(await get_document(session, owner_id, document_id))


@app.delete(
    "/documents/{document_id}",
    tags=["documents"],
    status_code=204,
    response_class=Response,
    summary="Delete a document",
    description="Delete an owned document and its stored chunks.",
    responses={**_DOCUMENT_RESPONSES, 404: _NOT_FOUND},
)
async def remove_document(document_id: UUID, owner_id: Owner, session: Session) -> Response:
    """Delete the document and return an empty response."""

    await delete_document(session, owner_id, document_id)
    return Response(status_code=204)


@app.get(
    "/health",
    tags=["system"],
    summary="Check service readiness",
    description="Check connectivity to PostgreSQL and the Ollama embedding service.",
    responses={
        503: {"model": HealthOut, "description": "At least one dependency is unavailable."},
        500: _DOCUMENT_RESPONSES[500],
    },
)
async def health(response: Response, session: Session, embedder: Embedder) -> HealthOut:
    """Report current dependency health and signal service unavailability."""

    report = await check_health(session, embedder)
    if report.status == "unavailable":
        response.status_code = 503
    return report
