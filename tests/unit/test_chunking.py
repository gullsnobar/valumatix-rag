"""Verify chunk text, structure, and metadata on corpus and synthetic inputs."""

from pathlib import Path

import pytest

from app.config import Settings
from app.ingestion.chunking import chunk_document, chunk_fixed, chunk_structure
from app.ingestion.extractors import (
    SUPPORTED_EXTENSIONS,
    ExtractedDocument,
    ExtractedSection,
    extract_document,
)


def _document(*sections: ExtractedSection) -> ExtractedDocument:
    return ExtractedDocument("example.md", "md", list(sections), [])


def _words(count: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{index}" for index in range(count))


def _text_corpus_paths(corpus_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in corpus_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and path.name != "scanned_office_notice.pdf"
    )


@pytest.fixture
def chunk_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Build settings with test credentials and the configured default chunk limits."""

    for name in ("CHUNK_SIZE_WORDS", "CHUNK_OVERLAP_WORDS", "CHUNK_MAX_WORDS"):
        monkeypatch.delenv(name, raising=False)

    return Settings(
        _env_file=None,
        postgres_user="test",
        postgres_password="test-db-password",
        postgres_db="test",
        database_url="postgresql://test:test-db-password@localhost/test",
        groq_api_key="test-groq-key",
        jwt_secret="test-jwt-secret",
        chunk_strategy="structure",
    )


def test_both_strategies_on_every_text_bearing_file(
    corpus_dir: Path, chunk_settings: Settings
) -> None:
    """Check positions, context headers, limits, and table headers across the corpus."""

    paths = _text_corpus_paths(corpus_dir)
    assert paths

    size = chunk_settings.chunk_size_words
    overlap = chunk_settings.chunk_overlap_words
    maximum = chunk_settings.chunk_max_words
    for path in paths:
        doc = extract_document(path.read_bytes(), path.name)
        fixed_chunks = chunk_fixed(doc, size, overlap)
        structure_chunks = chunk_structure(doc, size, maximum)

        for chunks in (fixed_chunks, structure_chunks):
            assert chunks, path.name
            assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
            for chunk in chunks:
                header = f"Document: {path.name} | Section: {chunk.section or 'n/a'}\n\n"
                assert chunk.embed_text == header + chunk.text
                assert chunk.word_count == len(chunk.text.split())

        for chunk in structure_chunks:
            assert chunk.word_count <= maximum, path.name
            rows = [line for line in chunk.text.splitlines() if line.startswith("|")]
            if rows:
                assert any(row.startswith(("|---", "| ---")) for row in rows), path.name


@pytest.mark.parametrize(
    "check_overview",
    [
        pytest.param(False, id="other-corpus-files"),
        pytest.param(
            True,
            id="company-overview",
            marks=pytest.mark.xfail(
                strict=True,
                raises=AssertionError,
                reason="Each overview slide has under 40 words and occupies its own page.",
            ),
        ),
    ],
)
def test_structure_chunk_minimum_across_corpus(
    corpus_dir: Path, chunk_settings: Settings, check_overview: bool
) -> None:
    """Require forty words per structure chunk when a document has multiple chunks."""

    for path in _text_corpus_paths(corpus_dir):
        if (path.name == "company_overview.pptx") != check_overview:
            continue
        doc = extract_document(path.read_bytes(), path.name)
        chunks = chunk_document(doc, chunk_settings)
        if len(chunks) > 1:
            short = [(chunk.position, chunk.word_count) for chunk in chunks if chunk.word_count < 40]
            assert not short, f"{path.name}: short chunks (position, words): {short}"


def test_expense_policy_keeps_hotel_row_with_its_header(
    corpus_dir: Path, chunk_settings: Settings
) -> None:
    """Keep the lodging reimbursement amount alongside its column labels."""

    path = corpus_dir / "expense_policy.pdf"
    doc = extract_document(path.read_bytes(), path.name)
    chunks = chunk_structure(
        doc, chunk_settings.chunk_size_words, chunk_settings.chunk_max_words
    )
    assert any(
        any(line.startswith("|") and "Expense" in line for line in chunk.text.splitlines())
        and any(line.startswith("|") and "15,000" in line for line in chunk.text.splitlines())
        for chunk in chunks
    )


def test_fixed_windows_overlap_by_configured_words(chunk_settings: Settings) -> None:
    """Verify each adjacent pair shares the configured number of words."""

    doc = _document(ExtractedSection(_words(600), None, None))
    overlap = chunk_settings.chunk_overlap_words
    chunks = chunk_fixed(doc, chunk_settings.chunk_size_words, overlap)
    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:]):
        assert previous.text.split()[-overlap:] == current.text.split()[:overlap]
    assert chunks[-1].text.endswith("word599")


def test_fixed_uses_metadata_of_first_word() -> None:
    """Follow the source word even when a window crosses a page boundary."""

    doc = _document(
        ExtractedSection(_words(5, "first"), 1, "First"),
        ExtractedSection(_words(6, "second"), 2, "Second"),
    )
    chunks = chunk_fixed(doc, 4, 1)
    assert [(chunk.page, chunk.section) for chunk in chunks] == [
        (1, "First"), (1, "First"), (2, "Second"), (2, "Second")
    ]
    assert "second0" in chunks[1].text


@pytest.mark.parametrize("overlap", [10, 11])
def test_fixed_rejects_overlap_at_least_size(overlap: int) -> None:
    """Reject sizes that would produce a zero or negative step."""

    with pytest.raises(ValueError):
        chunk_fixed(_document(), 10, overlap)


def test_structure_splits_large_tables_into_complete_rows() -> None:
    """Repeat both table header lines and keep body rows in order."""

    header = "| Item | Cost |\n| --- | --- |"
    rows = [f"| Hotel {number} | 1,000 |" for number in range(5)]
    doc = _document(ExtractedSection("\n".join([header, *rows]), 1, "Costs"))
    chunks = chunk_structure(doc, 22, 22)
    assert len(chunks) == 3
    assert all(chunk.text.startswith(header + "\n") for chunk in chunks)
    assert all(chunk.word_count <= 22 for chunk in chunks)
    assert [line for chunk in chunks for line in chunk.text.splitlines()[2:]] == rows


def test_structure_prefers_sentences_and_bounds_a_long_sentence() -> None:
    """Keep fitting sentences whole and split a single overlong sentence by words."""

    sentences = [_words(45, "first") + ".", _words(45, "second") + "!"]
    long_sentence = _words(125, "long")
    doc = _document(ExtractedSection(" ".join([*sentences, long_sentence]), None, None))
    chunks = chunk_structure(doc, 50, 60)

    assert [chunk.text for chunk in chunks[:2]] == sentences
    assert [chunk.word_count for chunk in chunks] == [45, 45, 60, 60, 5]
    assert " ".join(chunk.text for chunk in chunks[2:]) == long_sentence


def test_structure_merges_sections_and_small_tails_on_their_own_page() -> None:
    """Keep first-block metadata while packing short sections and page tails."""

    doc = _document(
        ExtractedSection(_words(22, "first"), 1, "First"),
        ExtractedSection(_words(20, "second"), 1, "Second"),
        ExtractedSection(_words(12, "tail"), 1, "Tail"),
        ExtractedSection(_words(10, "next"), 2, "Next page"),
    )
    chunks = chunk_structure(doc, 45, 60)
    assert [(chunk.page, chunk.section, chunk.word_count) for chunk in chunks] == [
        (1, "First", 54), (2, "Next page", 10)
    ]


@pytest.mark.parametrize(
    ("section_sizes", "expected"),
    [
        pytest.param((20, 100, 70), [("First", 120), ("Last", 70)], id="first-into-next"),
        pytest.param((130, 25, 100), [("First", 130), ("Middle", 125)], id="previous-too-large"),
        pytest.param((95, 25, 100), [("First", 120), ("Last", 100)], id="prefer-previous"),
    ],
)
def test_structure_merges_short_chunks_with_eligible_neighbors(
    section_sizes: tuple[int, int, int], expected: list[tuple[str, int]]
) -> None:
    """Prefer the previous chunk and fall forward when it cannot absorb the short chunk."""

    headings = ("First", "Middle", "Last")
    doc = _document(
        *(
            ExtractedSection(_words(size, heading.lower()), 1, heading)
            for heading, size in zip(headings, section_sizes)
        )
    )
    chunks = chunk_structure(doc, 110, 140)
    assert [(chunk.section, chunk.word_count) for chunk in chunks] == expected
    assert [chunk.position for chunk in chunks] == [0, 1]
    assert " ".join(chunk.text.replace("\n\n", " ") for chunk in chunks) == " ".join(
        section.text for section in doc.sections
    )


def test_chunk_document_respects_configured_strategy(chunk_settings: Settings) -> None:
    """Forward the configured limits and select the requested strategy."""

    doc = _document(ExtractedSection(_words(600), None, None))
    size = chunk_settings.chunk_size_words
    assert chunk_document(doc, chunk_settings) == chunk_structure(
        doc, size, chunk_settings.chunk_max_words
    )
    fixed_settings = chunk_settings.model_copy(update={"chunk_strategy": "fixed"})
    assert chunk_document(doc, fixed_settings) == chunk_fixed(
        doc, size, fixed_settings.chunk_overlap_words
    )


def test_settings_repr_hides_credentials(chunk_settings: Settings) -> None:
    """Keep key, token, and database credential values out of settings reprs."""

    for secret in ("test-groq-key", "test-jwt-secret", "test-db-password"):
        assert secret not in repr(chunk_settings)
