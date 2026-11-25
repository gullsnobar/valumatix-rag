"""Define custom exceptions and consistent JSON error responses."""


class RagServiceError(Exception):
    """Base exception for errors raised by the RAG service."""


class UnsupportedFileTypeError(RagServiceError):
    """Indicate that an uploaded file type is not supported."""


class NoExtractableTextError(RagServiceError):
    """Indicate that a file is empty, scanned, or otherwise has no usable text."""


class CorruptFileError(RagServiceError):
    """Indicate that an uploaded file cannot be parsed."""
