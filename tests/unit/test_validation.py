"""Check upload validation independently of the database and embedding service."""

import pytest

from app.config import Settings
from app.errors import CorruptFileError, FileTooLargeError
from app.ingestion.validation import sanitize_filename, validate_upload


@pytest.fixture
def upload_settings() -> Settings:
    """Provide explicit test-only settings without loading the project's .env file."""

    return Settings(
        _env_file=None,
        postgres_user="test",
        postgres_password="test",
        postgres_db="test",
        database_url="postgresql+asyncpg://localhost/test",
        groq_api_key="test",
        jwt_secret="test",
        max_upload_mb=1,
    )


def test_sanitize_filename() -> None:
    """Remove directory paths and control characters while retaining useful names."""

    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("C:\\some\\folder\\file\x00.txt") == "file.txt"
    long_name = sanitize_filename("a" * 260 + ".pdf")
    assert len(long_name) == 255
    assert long_name.endswith(".pdf")


@pytest.mark.parametrize(
    ("name", "data", "extension"),
    [
        ("policy.PDF", b"%PDF-1.7", ".pdf"),
        ("policy.docx", b"PK\x03\x04", ".docx"),
        ("slides.pptx", b"PK\x03\x04", ".pptx"),
        ("intro.md", "Résumé".encode(), ".md"),
        ("intro.txt", "Résumé".encode("cp1252"), ".txt"),
    ],
)
def test_accept_matching_signatures(
    upload_settings: Settings, name: str, data: bytes, extension: str
) -> None:
    """Accept matching binary signatures and either supported text encoding."""

    assert validate_upload(name, data, upload_settings) == extension


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("policy.pdf", b"PK\x03\x04"),
        ("policy.docx", b"%PDF"),
        ("slides.pptx", b"not a ZIP"),
        ("intro.md", b"hello\x00world"),
        ("intro.txt", b"\x81"),
    ],
)
def test_reject_bad_signatures(upload_settings: Settings, name: str, data: bytes) -> None:
    """Reject signatures and encodings that do not match the file type."""

    with pytest.raises(CorruptFileError):
        validate_upload(name, data, upload_settings)


def test_upload_size_limit(upload_settings: Settings) -> None:
    """Accept an upload at the byte limit and reject one byte over it."""

    data = b"x" * upload_settings.max_upload_bytes
    assert validate_upload("limit.txt", data, upload_settings) == ".txt"
    with pytest.raises(FileTooLargeError):
        validate_upload("limit.txt", data + b"x", upload_settings)
