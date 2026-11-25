"""Define custom exceptions and consistent JSON error responses."""

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
