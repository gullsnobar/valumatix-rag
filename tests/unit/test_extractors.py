"""Test structured text extraction against the project corpus."""

from pathlib import Path

import pytest

from app.errors import (
    CorruptFileError,
    NoExtractableTextError,
    UnsupportedFileTypeError,
)
from app.ingestion.extractors import (
    SUPPORTED_EXTENSIONS,
    ExtractedDocument,
    extract_document,
)


def _extract_file(path: Path) -> ExtractedDocument:
    return extract_document(path.read_bytes(), path.name)


def test_every_supported_corpus_file_extracts_meaningful_text(
    corpus_dir: Path,
) -> None:
    """Extract more than 100 characters from every non-scanned corpus file."""

    paths = sorted(
        path
        for path in corpus_dir.iterdir()
        if path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.name != "scanned_office_notice.pdf"
    )

    assert paths
    for path in paths:
        document = _extract_file(path)
        assert document.total_chars > 100, path.name


def test_scanned_pdf_has_no_extractable_text(corpus_dir: Path) -> None:
    """Reject a scanned PDF that has no text layer."""

    path = corpus_dir / "scanned_office_notice.pdf"
    with pytest.raises(NoExtractableTextError):
        _extract_file(path)


def test_pdf_tables_are_markdown(corpus_dir: Path) -> None:
    """Preserve the expense limits table as Markdown rows."""

    document = _extract_file(corpus_dir / "expense_policy.pdf")
    table_rows = [
        line
        for section in document.sections
        for line in section.text.splitlines()
        if line.startswith("|")
    ]

    assert any("15,000" in row for row in table_rows)


def test_docx_tables_are_markdown(corpus_dir: Path) -> None:
    """Preserve the leave entitlement table from the DOCX file."""

    document = _extract_file(corpus_dir / "leave_policy_v1_2024.docx")

    assert any(
        "18 working days" in line and line.startswith("|")
        for section in document.sections
        for line in section.text.splitlines()
    )


def test_docx_hidden_text_emits_warning(corpus_dir: Path) -> None:
    """Flag hidden Word text while keeping it in extracted content."""

    document = _extract_file(corpus_dir / "code_of_conduct.docx")

    assert any("Hidden text" in warning for warning in document.warnings)


def test_pptx_preserves_slide_order_and_titles(corpus_dir: Path) -> None:
    """Assign ordered page numbers and slide titles to PowerPoint sections."""

    document = _extract_file(corpus_dir / "company_overview.pptx")

    assert [section.page for section in document.sections] == list(
        range(1, len(document.sections) + 1)
    )
    assert any(section.section == "Our Values" for section in document.sections)


def test_markdown_splits_on_level_two_headings(corpus_dir: Path) -> None:
    """Use Markdown level-one and level-two headings as section boundaries."""

    document = _extract_file(corpus_dir / "security_it_policy.md")

    assert any(
        section.section == "3. Incident Reporting" for section in document.sections
    )


def test_unknown_extension_is_rejected() -> None:
    """Reject files whose extension is not in the supported set."""

    with pytest.raises(UnsupportedFileTypeError):
        extract_document(b"any bytes", "notes.xlsx")


def test_broken_pdf_is_rejected() -> None:
    """Translate invalid PDF input into a document extraction error."""

    with pytest.raises((CorruptFileError, NoExtractableTextError)):
        extract_document(b"this is not a PDF", "broken.pdf")
