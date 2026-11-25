"""Define custom exceptions and consistent JSON error responses."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from uuid import UUID


class RagServiceError(Exception):
    """Base exception for errors raised by the RAG service."""

    status_code = 500
    error_code = "internal_error"


class EmptyFileError(RagServiceError):
    """Indicate that an uploaded file has zero bytes."""

    status_code = 400
    error_code = "empty_file"


class UnsupportedFileTypeError(RagServiceError):
    """Indicate that an uploaded file type is not supported."""

    status_code = 415
    error_code = "unsupported_file_type"


class NoExtractableTextError(RagServiceError):
    """Indicate that a file is empty, scanned, or otherwise has no usable text."""

    status_code = 400
    error_code = "no_extractable_text"


class CorruptFileError(RagServiceError):
    """Indicate that an uploaded file cannot be parsed."""

    status_code = 400
    error_code = "corrupt_file"


class FileTooLargeError(RagServiceError):
    """Indicate that a file exceeds the configured upload limit."""

    status_code = 413
    error_code = "file_too_large"


class DuplicateDocumentError(RagServiceError):
    """Identify the document that already contains the same bytes."""

    status_code = 409
    error_code = "duplicate_document"

    def __init__(self, existing_document_id: UUID) -> None:
        """Keep the existing ID available to callers and in the response message."""

        self.existing_document_id = existing_document_id
        super().__init__(f"This file already exists as document {existing_document_id}.")


class DocumentNotFoundError(RagServiceError):
    """Indicate that the requested document is unavailable to the current owner."""

    status_code = 404
    error_code = "document_not_found"


class ExternalServiceError(RagServiceError):
    """Indicate that a dependency failed or timed out."""

    status_code = 503
    error_code = "service_unavailable"


class UnauthorizedError(RagServiceError):
    """Reject a request without a valid bearer token."""

    status_code = 401
    error_code = "unauthorized"

    def __init__(self) -> None:
        """Provide a generic message for every bearer-token failure."""

        super().__init__("A valid bearer token is required.")


class InvalidCredentialsError(RagServiceError):
    """Reject an unsuccessful login without revealing whether the email exists."""

    status_code = 401
    error_code = "invalid_credentials"

    def __init__(self) -> None:
        """Use the same response for unknown emails and incorrect passwords."""

        super().__init__("Invalid email or password.")


class EmailTakenError(RagServiceError):
    """Report a duplicate signup email."""

    status_code = 409
    error_code = "email_taken"

    def __init__(self) -> None:
        """Report that the supplied email is already registered."""

        super().__init__("This email is already registered.")


class RateLimitedError(RagServiceError):
    """Report a provider rate limit along with its requested wait time."""

    status_code = 429
    error_code = "rate_limited"

    def __init__(self, retry_after_seconds: float) -> None:
        """Keep the retry delay available to callers."""

        self.retry_after_seconds = retry_after_seconds
        super().__init__("Language model rate limit reached.")

    @classmethod
    def from_retry_after(cls, header: str | None) -> "RateLimitedError":
        """Parse a Retry-After value as seconds or an HTTP date, defaulting to ten."""

        if header is not None:
            try:
                seconds = float(header)
                if isfinite(seconds) and seconds >= 0:
                    return cls(seconds)
            except ValueError:
                try:
                    when = parsedate_to_datetime(header)
                    if when.tzinfo is not None:
                        return cls(max(0.0, (when - datetime.now(UTC)).total_seconds()))
                except (ValueError, OverflowError):
                    pass
        return cls(10.0)
