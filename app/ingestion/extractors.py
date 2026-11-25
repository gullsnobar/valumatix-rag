"""Extract text from PDF, DOCX, PPTX, Markdown, and plain-text files."""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pymupdf4llm
from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pptx import Presentation

from app.errors import (
    CorruptFileError,
    NoExtractableTextError,
    UnsupportedFileTypeError,
)

LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".md", ".txt"}

_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_DOCX_HEADING_LEVEL = re.compile(r"^Heading\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedSection:
    """Represent a logical section extracted from a source document."""

    text: str
    page: int | None
    section: str | None


@dataclass(frozen=True)
class ExtractedDocument:
    """Contain normalized sections and extraction metadata for one document."""

    filename: str
    file_type: str
    sections: list[ExtractedSection]
    warnings: list[str]

    @property
    def total_chars(self) -> int:
        """Return the total number of characters across extracted sections."""

        return sum(len(section.text) for section in self.sections)


def extract_document(data: bytes, filename: str) -> ExtractedDocument:
    """Extract and normalize structured text from a supported document."""

    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file type '{extension or '<none>'}' for {filename}."
        )

    extractors = {
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".pptx": _extract_pptx,
        ".md": _extract_markdown,
        ".txt": _extract_text,
    }

    try:
        raw_sections, warnings = extractors[extension](data, filename)
    except Exception as exc:
        raise CorruptFileError(f"Could not parse {filename}.") from exc

    sections = [
        ExtractedSection(
            text=normalized_text,
            page=section.page,
            section=_normalize_text(section.section) if section.section else None,
        )
        for section in raw_sections
        if (normalized_text := _normalize_text(section.text))
    ]
    document = ExtractedDocument(
        filename=filename,
        file_type=extension.lstrip("."),
        sections=sections,
        warnings=warnings,
    )

    non_whitespace_chars = sum(
        len(re.sub(r"\s+", "", section.text)) for section in document.sections
    )
    if non_whitespace_chars < 20:
        raise NoExtractableTextError(
            f"No extractable text found in {filename}; the file may be scanned or empty."
        )

    return document


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\x00", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _extract_pdf(
    data: bytes, filename: str
) -> tuple[list[ExtractedSection], list[str]]:
    sections: list[ExtractedSection] = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page_index, page in enumerate(document):
            try:
                chunks = pymupdf4llm.to_markdown(
                    document,
                    pages=[page_index],
                    page_chunks=True,
                )
                page_text = chunks[0]["text"] if chunks else ""
            except Exception:
                LOGGER.warning(
                    "Markdown PDF extraction failed for %s page %d; using plain text.",
                    filename,
                    page_index + 1,
                    exc_info=True,
                )
                page_text = page.get_text("text")

            heading_match = _MARKDOWN_HEADING.search(page_text)
            heading = _clean_markdown_heading(heading_match.group(1)) if heading_match else None
            sections.append(
                ExtractedSection(
                    text=page_text,
                    page=page_index + 1,
                    section=heading,
                )
            )
    return sections, []


def _clean_markdown_heading(heading: str) -> str:
    return heading.strip().strip("*_` ")


def _extract_docx(
    data: bytes, filename: str
) -> tuple[list[ExtractedSection], list[str]]:
    document = Document(io.BytesIO(data))
    warnings = _detect_hidden_docx_text(document, filename)
    sections: list[ExtractedSection] = []
    block_lines: list[str] = []
    block_heading: str | None = None

    def flush_block() -> None:
        if block_lines:
            sections.append(
                ExtractedSection(
                    text="\n\n".join(block_lines),
                    page=None,
                    section=block_heading,
                )
            )

    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            heading_level = _docx_heading_level(paragraph)
            if heading_level == 1:
                flush_block()
                block_lines = []
                block_heading = text
            if heading_level is not None:
                block_lines.append(f"{'#' * heading_level} {text}")
            else:
                block_lines.append(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            markdown_table = _docx_table_to_markdown(table)
            if markdown_table:
                block_lines.append(markdown_table)

    flush_block()
    return sections, warnings


def _docx_heading_level(paragraph: Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    if style_name.lower() == "title":
        return 1
    match = _DOCX_HEADING_LEVEL.match(style_name)
    if not match:
        return None
    return min(int(match.group(1)), 3)


def _docx_table_to_markdown(table: Table) -> str:
    rows = [
        [_escape_markdown_cell(cell.text) for cell in row.cells]
        for row in table.rows
    ]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (width - len(row)) for row in rows]
    header = f"| {' | '.join(padded_rows[0])} |"
    separator = f"| {' | '.join(['---'] * width)} |"
    body = [f"| {' | '.join(row)} |" for row in padded_rows[1:]]
    return "\n".join([header, separator, *body])


def _escape_markdown_cell(text: str) -> str:
    return _normalize_text(text).replace("|", "\\|").replace("\n", "<br>")


def _detect_hidden_docx_text(document: DocxDocument, filename: str) -> list[str]:
    warnings: list[str] = []
    seen_snippets: set[str] = set()
    for paragraph in _iter_docx_paragraphs(document):
        for run in paragraph.runs:
            font_size = run.font.size
            font_color = run.font.color.rgb
            is_tiny = font_size is not None and font_size.pt < 4
            is_white = font_color is not None and str(font_color).upper() == "FFFFFF"
            snippet = _normalize_text(run.text)[:60]
            if (is_tiny or is_white) and snippet and snippet not in seen_snippets:
                warnings.append(f"Hidden text detected in {filename}: '{snippet}'")
                seen_snippets.add(snippet)
    return warnings


def _iter_docx_paragraphs(document: DocxDocument) -> Iterable[Paragraph]:
    yield from document.paragraphs
    for table in document.tables:
        yield from _iter_table_paragraphs(table)


def _iter_table_paragraphs(table: Table) -> Iterable[Paragraph]:
    for row in table.rows:
        for cell in row.cells:
            yield from cell.paragraphs
            for nested_table in cell.tables:
                yield from _iter_table_paragraphs(nested_table)


def _extract_pptx(
    data: bytes, filename: str
) -> tuple[list[ExtractedSection], list[str]]:
    del filename
    presentation = Presentation(io.BytesIO(data))
    sections: list[ExtractedSection] = []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape and title_shape.text else None
        parts: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                shape_text = "\n".join(
                    paragraph.text for paragraph in shape.text_frame.paragraphs
                ).strip()
                if shape_text:
                    parts.append(shape_text)
            if getattr(shape, "has_table", False):
                table_rows = [
                    [_escape_markdown_cell(cell.text) for cell in row.cells]
                    for row in shape.table.rows
                ]
                table_text = _rows_to_markdown_table(table_rows)
                if table_text:
                    parts.append(table_text)

        if slide.has_notes_slide:
            notes_text = slide.notes_slide.notes_text_frame.text.strip()
            if notes_text:
                parts.append(f"Notes: {notes_text}")

        sections.append(
            ExtractedSection(
                text="\n\n".join(parts),
                page=slide_number,
                section=title,
            )
        )
    return sections, []


def _rows_to_markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded_rows = [row + [""] * (width - len(row)) for row in rows]
    return "\n".join(
        [
            f"| {' | '.join(padded_rows[0])} |",
            f"| {' | '.join(['---'] * width)} |",
            *(f"| {' | '.join(row)} |" for row in padded_rows[1:]),
        ]
    )


def _extract_markdown(
    data: bytes, filename: str
) -> tuple[list[ExtractedSection], list[str]]:
    del filename
    text = data.decode("utf-8", errors="replace")
    sections: list[ExtractedSection] = []
    section_lines: list[str] = []
    section_name: str | None = None

    def flush_section() -> None:
        if section_lines:
            sections.append(
                ExtractedSection(
                    text="\n".join(section_lines),
                    page=None,
                    section=section_name,
                )
            )

    for line in text.splitlines():
        heading_match = re.match(r"^(#{1,2})\s+(.+?)\s*$", line)
        if heading_match:
            flush_section()
            section_lines = [line]
            section_name = heading_match.group(2).strip()
        else:
            section_lines.append(line)
    flush_section()
    return sections, []


def _extract_text(
    data: bytes, filename: str
) -> tuple[list[ExtractedSection], list[str]]:
    del filename
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    return [ExtractedSection(text=text, page=None, section=None)], []
