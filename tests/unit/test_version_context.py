"""Verify version header extraction and its representation in generation prompts."""

from uuid import UUID

from app.generation import build_messages
from app.ingestion.extractors import ExtractedDocument, ExtractedSection
from app.ingestion.pipeline import _document_header
from app.retrieval import RetrievedChunk


def test_document_header_uses_first_two_nonempty_lines() -> None:
    """Capture title and version from separate sections while bounding the header."""

    document = ExtractedDocument(
        "policy.pdf", "pdf",
        [
            ExtractedSection("\n # Leave policy \n\n", 1, "Leave policy"),
            ExtractedSection("\nVersion 2.0 — effective July 2026\nAnnual leave.", 1, None),
        ],
        [],
    )
    assert _document_header(document) == "# Leave policy\nVersion 2.0 — effective July 2026"
    long_document = ExtractedDocument(
        "policy.txt", "txt", [ExtractedSection("A" * 198 + "\nVersion 2", None, None)], []
    )
    assert len(_document_header(long_document) or "") == 200


def test_generation_uses_escaped_document_header_and_citation_examples() -> None:
    """Pass new source metadata safely and demonstrate adjacent citation markers."""

    chunk = RetrievedChunk(
        UUID(int=1), UUID(int=2), "policy.pdf", 1, None, 0, "Leave", 0.8,
        citation_id="C1", doc_header='Leave "Policy" & Benefits\nVersion 2.0',
    )
    system, user = build_messages("How much leave?", [chunk])
    assert 'doc="Leave &quot;Policy&quot; &amp; Benefits\nVersion 2.0"' in user["content"]
    assert "NEWEST" in system["content"]
    assert "[C1][C3]" in system["content"]
    assert "Example:" in system["content"]
