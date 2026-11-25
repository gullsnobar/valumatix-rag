"""Define strategies for splitting extracted text into chunks."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, replace
from itertools import groupby

from app.config import Settings
from app.ingestion.extractors import ExtractedDocument, ExtractedSection

_MIN_CHUNK_WORDS = 40
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])(?=\s)")
_TABLE_SEPARATOR = re.compile(r"\| *:?-+:? *(?:\| *:?-+:? *)*\|?")
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    """Store text, embedding input, and the location of a chunk's first content."""

    text: str
    embed_text: str
    position: int
    page: int | None
    section: str | None
    word_count: int


def chunk_fixed(
    doc: ExtractedDocument, size_words: int, overlap_words: int
) -> list[Chunk]:
    """Return overlapping word windows with metadata from each window's first word."""

    if size_words <= 0 or not 0 <= overlap_words < size_words:
        raise ValueError("Require a positive size and 0 <= overlap_words < size_words.")

    words: list[str] = []
    sources: list[ExtractedSection] = []
    for section in doc.sections:
        section_words = section.text.split()
        words.extend(section_words)
        sources.extend([section] * len(section_words))

    chunks: list[Chunk] = []
    step = size_words - overlap_words
    for start in range(0, len(words), step):
        end = min(start + size_words, len(words))
        source = sources[start]
        chunks.append(
            _make_chunk(
                doc.filename,
                " ".join(words[start:end]),
                len(chunks),
                source.page,
                source.section,
            )
        )
        if end == len(words):
            break
    return chunks


def chunk_structure(
    doc: ExtractedDocument, target_words: int, max_words: int
) -> list[Chunk]:
    """Pack text and table blocks into chunks within each source page.

    Merge chunks under 40 words into the previous chunk on the same page
    if the result fits within max_words, otherwise try the next chunk on
    that page with the same limit. Keep the chunk if neither neighbor fits.
    Renumber the resulting chunks in document order.

    A table row that exceeds the maximum with its header stays intact.
    """

    if not 0 < target_words <= max_words:
        raise ValueError("Require 0 < target_words <= max_words.")

    chunks: list[Chunk] = []
    for page, sections in groupby(doc.sections, key=lambda section: section.page):
        parts: list[str] = []
        word_count = 0
        heading: str | None = None

        for section in sections:
            for block in _section_blocks(section.text, max_words):
                block_words = len(block.split())
                if parts and word_count + block_words > target_words:
                    chunks.append(
                        _make_chunk(
                            doc.filename, "\n\n".join(parts), len(chunks), page, heading
                        )
                    )
                    parts = []
                    word_count = 0
                if not parts:
                    heading = section.section
                parts.append(block)
                word_count += block_words

        if parts:
            chunks.append(
                _make_chunk(doc.filename, "\n\n".join(parts), len(chunks), page, heading)
            )

    return _merge_short_chunks(doc.filename, chunks, max_words)


def chunk_document(doc: ExtractedDocument, settings: Settings) -> list[Chunk]:
    """Chunk an extracted document using the configured strategy and word limits."""

    if settings.chunk_strategy == "fixed":
        return chunk_fixed(doc, settings.chunk_size_words, settings.chunk_overlap_words)
    return chunk_structure(doc, settings.chunk_size_words, settings.chunk_max_words)


def _make_chunk(
    filename: str, text: str, position: int, page: int | None, section: str | None
) -> Chunk:
    # Including the document and section names improves retrieval for short chunks.
    header = f"Document: {filename} | Section: {section or 'n/a'}\n\n"
    return Chunk(text, header + text, position, page, section, len(text.split()))


def _merge_short_chunks(
    filename: str, chunks: list[Chunk], max_words: int
) -> list[Chunk]:
    pending = deque(chunks)
    merged: list[Chunk] = []
    while pending:
        chunk = pending.popleft()
        if chunk.word_count < _MIN_CHUNK_WORDS:
            if merged and _can_merge(merged[-1], chunk, max_words):
                pending.appendleft(_join_chunks(filename, merged.pop(), chunk))
                continue
            if pending and _can_merge(chunk, pending[0], max_words):
                pending.appendleft(_join_chunks(filename, chunk, pending.popleft()))
                continue
        merged.append(chunk)

    return [replace(chunk, position=position) for position, chunk in enumerate(merged)]


def _can_merge(first: Chunk, second: Chunk, max_words: int) -> bool:
    return first.page == second.page and first.word_count + second.word_count <= max_words


def _join_chunks(filename: str, first: Chunk, second: Chunk) -> Chunk:
    return _make_chunk(
        filename,
        f"{first.text}\n\n{second.text}",
        first.position,
        first.page,
        first.section,
    )


def _line_kind(line: str) -> str:
    if not line.strip():
        return "blank"
    return "table" if line.lstrip().startswith("|") else "prose"


def _section_blocks(text: str, max_words: int) -> Iterator[str]:
    for kind, lines in groupby(text.splitlines(), key=_line_kind):
        if kind == "blank":
            continue
        block = "\n".join(lines).strip()
        if len(block.split()) <= max_words:
            yield block
        elif kind == "table":
            yield from _split_table(block, max_words)
        else:
            yield from _split_prose(block, max_words)


def _split_table(block: str, max_words: int) -> Iterator[str]:
    rows = block.splitlines()
    header: list[str] = []
    if len(rows) >= 2 and _TABLE_SEPARATOR.fullmatch(rows[1].strip()):
        header, rows = rows[:2], rows[2:]

    header_words = sum(len(line.split()) for line in header)
    part: list[str] = []
    word_count = header_words
    for row in rows:
        row_words = len(row.split())
        if part and word_count + row_words > max_words:
            yield "\n".join([*header, *part])
            part = []
            word_count = header_words
        part.append(row)
        word_count += row_words

    if header or part:
        yield "\n".join([*header, *part])


def _split_prose(block: str, max_words: int) -> Iterator[str]:
    sentences: list[str] = []
    word_count = 0
    for sentence in _SENTENCE_BREAK.split(block):
        words = list(_WORD.finditer(sentence))
        if sentences and word_count + len(words) > max_words:
            yield "".join(sentences).strip()
            sentences = []
            word_count = 0

        # A sentence without an earlier breakpoint can still exceed the word limit.
        for start in range(0, len(words), max_words):
            end = start + max_words
            if end >= len(words):
                sentences.append(sentence[words[start].start() :] if start else sentence)
                word_count += len(words) - start
            else:
                yield sentence[words[start].start() : words[end - 1].end()]

    if sentences:
        yield "".join(sentences).strip()
