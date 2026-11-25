"""Define the FastAPI application and routes without business logic."""

import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, AsyncExitStack
from http import HTTPStatus
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.asking import AskService
from app.config import PUBLIC_OWNER_ID, Settings, get_settings
from app.db import engine, get_session, init_db
from app.errors import RagServiceError
from app.health import check_health
from app.ingestion.pipeline import ingest_document
from app.llm_client import ChatClient, EmbeddingClient, get_chat_client, get_embedding_client
from app.logging_config import RequestIdMiddleware, configure_logging
from app.repository import compute_metrics, delete_document, get_document, list_documents
from app.schemas import (
    AskRequest, AskResponse, DocumentListOut, DocumentOut, ErrorBody, ErrorResponse,
    HealthOut, MetricsOut,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Initialize and close the database engine and shared HTTP clients."""

    configure_logging()
    try:
        await init_db()
        async with AsyncExitStack() as resources:
            embedder = EmbeddingClient(get_settings())
            resources.push_async_callback(embedder.aclose)
            chat = ChatClient(get_settings())
            resources.push_async_callback(chat.aclose)
            application.state.embedding_client = embedder
            application.state.chat_client = chat
            yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Tarnwick RAG Service",
    version="0.1.0",
    description="Manage documents and get source-cited answers for Tarnwick Consulting.",
    lifespan=lifespan,
)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
_ask_limit = limiter.shared_limit(lambda: get_settings().rate_limit_ask, scope="ask")


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


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return the standard error envelope when the request limit is exceeded."""

    return _error_response(request, 429, "rate_limited", "Too many requests. Please try again later.")


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
Chat = Annotated[ChatClient, Depends(get_chat_client)]
ServiceSettings = Annotated[Settings, Depends(get_settings)]

_DOCUMENT_RESPONSES = {
    422: {"model": ErrorResponse, "description": "Request validation failed."},
    503: {"model": ErrorResponse, "description": "A required dependency is unavailable."},
    500: {"model": ErrorResponse, "description": "An unexpected error occurred."},
}
_NOT_FOUND = {"model": ErrorResponse, "description": "The document was not found."}
_RATE_LIMIT = {"model": ErrorResponse, "description": "The request rate exceeded the limit."}
_ASK_RESPONSES = {
    **_DOCUMENT_RESPONSES,
    429: _RATE_LIMIT,
    503: {
        "model": ErrorResponse,
        "description": "A required dependency is unavailable.",
        "content": {
            "application/json": {
                "example": {
                    "error": {
                        "code": "service_unavailable",
                        "message": "Language model unavailable",
                        "request_id": "518c9510-a3cf-4493-9260-92637bf6ff89",
                    }
                }
            }
        },
    },
}


def get_ask_service(
    request: Request, session: Session, embedder: Embedder, chat: Chat,
    settings: ServiceSettings, owner_id: Owner,
) -> AskService:
    """Assemble request-scoped dependencies for both ask routes."""

    return AskService(session, embedder, chat, settings, owner_id, request.state.request_id)


Asking = Annotated[AskService, Depends(get_ask_service)]


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
        429: _RATE_LIMIT,
    },
)
@limiter.limit(lambda: get_settings().rate_limit_upload)
async def upload_document(
    request: Request,
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


@app.post(
    "/ask",
    tags=["ask"],
    summary="Ask a question",
    description="Answer from the current owner's documents and validate source citations.",
    responses=_ASK_RESPONSES,
)
@_ask_limit
async def ask(request: Request, question: AskRequest, service: Asking) -> AskResponse:
    """Return the graph's final validated result."""

    return await service.answer(question)


@app.post(
    "/ask/stream",
    tags=["ask"],
    summary="Stream an answer",
    description="Receive live stages, validated answer tokens, and a terminal done or error event.",
    response_class=StreamingResponse,
    responses={
        **_ASK_RESPONSES,
        200: {
            "description": "Server-sent events. Replace the displayed answer with done.answer.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
    },
)
@_ask_limit
async def ask_stream(request: Request, question: AskRequest, service: Asking) -> StreamingResponse:
    """Serve the graph's stages and validated text as SSE."""

    return StreamingResponse(
        service.stream(question),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get(
    "/metrics",
    tags=["system"],
    summary="Get answer metrics",
    description="Aggregate the current owner's ask activity over the last seven days.",
    responses=_DOCUMENT_RESPONSES,
)
async def metrics(session: Session, owner_id: Owner) -> MetricsOut:
    """Return aggregate question-answering telemetry."""

    return await compute_metrics(session, owner_id)
