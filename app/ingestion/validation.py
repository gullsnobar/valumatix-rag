"""Validate upload file types, sizes, and hashes for duplicate detection."""

import hashlib
from pathlib import PureWindowsPath
from unicodedata import category

from app.config import Settings
from app.errors import (
    CorruptFileError,
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.ingestion.extractors import SUPPORTED_EXTENSIONS

_MAX_FILENAME_LENGTH = 255
_MAGIC_BYTES = {".pdf": b"%PDF", ".docx": b"PK\x03\x04", ".pptx": b"PK\x03\x04"}


def sanitize_filename(name: str) -> str:
    """Keep a path-free filename, stripping control characters and limiting length."""

    base = PureWindowsPath(name).name
    cleaned = "".join(char for char in base if category(char) != "Cc")
    extension = PureWindowsPath(cleaned).suffix
    if len(cleaned) > _MAX_FILENAME_LENGTH and extension.lower() in SUPPORTED_EXTENSIONS:
        return cleaned[: _MAX_FILENAME_LENGTH - len(extension)] + extension
    return cleaned[:_MAX_FILENAME_LENGTH]


def validate_upload(filename: str, data: bytes, settings: Settings) -> str:
    """Validate size, supported extension, and expected file signature or encoding."""

    if not data:
        raise EmptyFileError("The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError(f"The upload limit is {settings.max_upload_mb} MB.")

    extension = PureWindowsPath(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError("The uploaded file type is not supported.")

    signature = _MAGIC_BYTES.get(extension)
    if signature is not None:
        if not data.startswith(signature):
            raise CorruptFileError("File contents do not match the file extension.")
    else:
        _validate_text(data)
    return extension


def _validate_text(data: bytes) -> None:
    if b"\x00" in data:
        raise CorruptFileError("Text files cannot contain NUL bytes.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            data.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise CorruptFileError("Text files must use UTF-8 or Windows-1252.") from exc


def compute_sha256(data: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of an upload."""

    return hashlib.sha256(data).hexdigest()
