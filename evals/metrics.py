"""Calculate retrieval hit rate at k, recall at k, and mean reciprocal rank."""

from collections.abc import Mapping, Sequence
from statistics import mean
from typing import Protocol, TypedDict


class ExpectedSource(TypedDict):
    """Name a source and the evidence substrings that can match it."""

    file: str
    evidence: list[str]


class GoldenItem(TypedDict):
    """Represent one question and its expected evidence and answer."""

    id: str
    question: str
    type: str
    language: str
    answerable: bool
    expected_sources: list[ExpectedSource]
    reference_answer: str
    key_facts: list[str]


class ChunkText(Protocol):
    """Identify the two fields that retrieval scoring needs from a chunk."""

    @property
    def filename(self) -> str:
        """Return the source filename."""
        ...

    @property
    def text(self) -> str:
        """Return the retrieved passage."""
        ...


type Chunk = ChunkText | Mapping[str, str]


def matches_source(chunk: Chunk, source: ExpectedSource) -> bool:
    """Require an exact filename and at least one literal evidence substring."""

    if isinstance(chunk, Mapping):
        filename, text = chunk["filename"], chunk["text"]
    else:
        filename, text = chunk.filename, chunk.text
    return filename == source["file"] and any(evidence in text for evidence in source["evidence"])


def hit_at_k(retrieved: Sequence[Chunk], item: GoldenItem, k: int) -> float | None:
    """Return one for any relevant top-k hit and omit unanswerable questions."""

    if not item["answerable"]:
        return None
    return float(any(
        matches_source(chunk, source)
        for chunk in retrieved[:k]
        for source in item["expected_sources"]
    ))


def recall_at_k(retrieved: Sequence[Chunk], item: GoldenItem, k: int) -> float | None:
    """Return the fraction of expected sources represented by relevant top-k chunks."""

    if not item["answerable"]:
        return None
    sources = item["expected_sources"]
    if not sources:
        return 0.0
    covered = sum(any(matches_source(chunk, source) for chunk in retrieved[:k]) for source in sources)
    return covered / len(sources)


def reciprocal_rank(retrieved: Sequence[Chunk], item: GoldenItem) -> float | None:
    """Return one divided by the first relevant rank, or zero for a miss."""

    if not item["answerable"]:
        return None
    for rank, chunk in enumerate(retrieved, 1):
        if any(matches_source(chunk, source) for source in item["expected_sources"]):
            return 1 / rank
    return 0.0


def aggregate(items: Sequence[Mapping[str, float | None]]) -> dict[str, float | None]:
    """Compute each metric's arithmetic mean over applicable item scores."""

    names = dict.fromkeys(key for item in items for key in item)
    result = {}
    for name in names:
        values = [value for item in items if (value := item.get(name)) is not None]
        result[name] = mean(values) if values else None
    return result
