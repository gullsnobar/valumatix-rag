"""Define Pydantic request and response models for the service API."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.config import get_settings

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


class AskRequest(BaseModel):
    """Accept a single question and an optional retrieval limit."""

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] = Field(
        description="Question to answer from the current owner's documents.",
        examples=["How many annual leave days do employees get?"],
    )
    top_k: int | None = Field(default=None, ge=1, le=10, description="Maximum sources to retrieve.")

    @field_validator("question")
    @classmethod
    def validate_question_length(cls, question: str) -> str:
        """Enforce the configured maximum question length."""

        maximum = get_settings().max_question_chars
        if len(question) > maximum:
            raise ValueError(f"Question must be at most {maximum} characters.")
        return question


class CitationOut(BaseModel):
    """Identify a source cited in the validated answer."""

    id: str = Field(description="Citation marker without brackets.", examples=["C1"])
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None
    section: str | None


class RetrievedChunkOut(BaseModel):
    """Expose a retrieved passage and the scores used to rank it."""

    citation_id: str
    chunk_id: UUID
    document_id: UUID
    filename: str
    page: int | None
    section: str | None
    text: str
    similarity: float = Field(description="Cosine similarity to the question.")
    keyword_rank: int | None
    rrf_score: float
    cited: bool


_LEAVE_SOURCE = {
    "chunk_id": "632b4876-32b3-4e1d-b826-3879b63ed92a",
    "document_id": "c034638b-64db-4c5d-8298-c10192d4772b",
    "filename": "leave_policy_v2_2026.pdf",
    "page": 1,
    "section": "Leave Entitlements",
}


class AskResponse(BaseModel):
    """Return the verified answer, evidence, provider, and timing information."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "answer": "Employees receive 21 working days of annual leave. [C1]",
                    "refused": False,
                    "refusal_reason": None,
                    "citations": [{"id": "C1", **_LEAVE_SOURCE}],
                    "chunks": [
                        {
                            "citation_id": "C1", **_LEAVE_SOURCE,
                            "text": "Annual leave: 21 working days.",
                            "similarity": 0.7591, "keyword_rank": 1, "rrf_score": 0.0328,
                            "cited": True,
                        }
                    ],
                    "retrieved_count": 1,
                    "provider": "groq",
                    "model": "openai/gpt-oss-20b",
                    "timings_ms": {"retrieve": 140.3, "generate": 310.5},
                    "prompt_tokens": 715,
                    "completion_tokens": 18,
                    "request_id": "518c9510-a3cf-4493-9260-92637bf6ff89",
                }
            ]
        }
    )

    answer: str
    refused: bool
    refusal_reason: str | None
    citations: list[CitationOut]
    chunks: list[RetrievedChunkOut]
    retrieved_count: int
    provider: str | None
    model: str | None
    timings_ms: dict[str, float]
    prompt_tokens: int
    completion_tokens: int
    request_id: str


class MetricsOut(BaseModel):
    """Summarize question-answering activity for the owner."""

    total_requests: int
    error_rate: float = Field(description="Fraction of requests that failed.")
    refusal_rate: float = Field(description="Fraction of requests refused by the workflow.")
    p50_latency_ms: float
    p95_latency_ms: float
    avg_latency_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    estimated_cost_usd: float
    provider_counts: dict[str, int]
    window: str
