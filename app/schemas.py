"""Define Pydantic request and response models for the service API."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_DOCUMENT_EXAMPLE = {
    "id": "c034638b-64db-4c5d-8298-c10192d4772b",
    "filename": "expense_policy.pdf",
    "file_type": "pdf",
    "size_bytes": 42000,
    "num_chunks": 2,
    "warnings": [],
    "created_at": "2026-11-25T12:00:00Z",
}
_ERROR_EXAMPLE = {
    "code": "document_not_found",
    "message": "Document not found.",
    "request_id": "518c9510-a3cf-4493-9260-92637bf6ff89",
}
ServiceStatus = Literal["ok", "unavailable"]


class DocumentOut(BaseModel):
    """Describe an ingested document without exposing private storage fields."""

    model_config = ConfigDict(
        from_attributes=True, json_schema_extra={"examples": [_DOCUMENT_EXAMPLE]}
    )

    id: UUID = Field(description="Unique document identifier.")
    filename: str = Field(description="Sanitized name of the uploaded file.")
    file_type: str = Field(description="Lowercase filename extension without the dot.")
    size_bytes: int = Field(description="Original upload size in bytes.")
    num_chunks: int = Field(description="Number of stored text chunks.")
    warnings: list[str] = Field(description="Warnings produced during text extraction.")
    created_at: datetime = Field(description="Timestamp at which the document was stored.")


class DocumentListOut(BaseModel):
    """List documents owned by the current caller."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"documents": [_DOCUMENT_EXAMPLE], "total": 1}]}
    )

    documents: list[DocumentOut] = Field(description="Documents ordered newest first.")
    total: int = Field(description="Total number of documents in the list.")


class ErrorBody(BaseModel):
    """Describe an API error and its correlation ID."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ERROR_EXAMPLE]})

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    request_id: str = Field(description="ID shared with the X-Request-ID response header.")


class ErrorResponse(BaseModel):
    """Wrap an API error in a consistent response envelope."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"error": _ERROR_EXAMPLE}]})

    error: ErrorBody = Field(description="Details of the request failure.")


class HealthOut(BaseModel):
    """Report overall readiness and the status of each dependency."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"status": "ok", "database": "ok", "embedding_service": "ok"},
                {
                    "status": "unavailable",
                    "database": "ok",
                    "embedding_service": "unavailable",
                },
            ]
        }
    )

    status: ServiceStatus = Field(description="Overall readiness.")
    database: ServiceStatus = Field(description="Result of the PostgreSQL connection check.")
    embedding_service: ServiceStatus = Field(description="Result of the Ollama connection check.")
