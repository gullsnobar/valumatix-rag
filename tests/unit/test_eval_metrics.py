"""Test evidence-aware retrieval scoring and provider-side evaluation behavior."""

import json
from dataclasses import dataclass

import httpx
import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.errors import RateLimitedError
from app.llm_client import ChatClient
from evals.judge import JudgeClient, parse_judgement
from evals.metrics import GoldenItem, aggregate, hit_at_k, recall_at_k, reciprocal_rank


@dataclass(frozen=True)
class Passage:
    """Provide a source filename and its retrieved text."""

    filename: str
    text: str


@pytest.fixture
def item() -> GoldenItem:
    """Require evidence covering two separate files."""

    return {
        "id": "example", "question": "What can I claim?", "type": "multi_doc",
        "language": "en", "answerable": True,
        "expected_sources": [
            {"file": "remote.md", "evidence": ["stipend", "15,000"]},
            {"file": "expense.md", "evidence": ["3,000"]},
        ],
        "reference_answer": "Office stipend and internet reimbursement.",
        "key_facts": ["Office stipend", "Internet reimbursement"],
    }


def test_hit_at_k_requires_the_filename_and_evidence(item: GoldenItem) -> None:
    """Exclude another filename and passages missing the annotated substring."""

    chunks = [
        Passage("other.md", "A stipend."),
        Passage("remote.md", "Schedule."),
        Passage("remote.md", "PKR 15,000 lump sum."),
    ]
    assert hit_at_k(chunks, item, 1) == 0
    assert hit_at_k(chunks, item, 2) == 0
    assert hit_at_k(chunks, item, 4) == 1


def test_recall_at_k_is_partial_for_a_multi_document_match(item: GoldenItem) -> None:
    """Count unique expected sources instead of counting repeated matches."""

    chunks = [
        Passage("remote.md", "A stipend."),
        Passage("remote.md", "PKR 15,000."),
        Passage("expense.md", "Meals and travel."),
        Passage("other.md", "A home internet claim of PKR 3,000."),
        Passage("expense.md", "Remote internet costs up to PKR 3,000."),
    ]
    assert recall_at_k(chunks, item, 4) == 0.5
    assert recall_at_k(chunks, item, 8) == 1


def test_mean_reciprocal_rank_excludes_unanswerable_items(item: GoldenItem) -> None:
    """Average reciprocal ranks over the answerable subset, including misses."""

    chunks = [Passage("other.md", "A stipend."), Passage("remote.md", "A stipend.")]
    assert reciprocal_rank(chunks, item) == 0.5
    assert reciprocal_rank([], item) == 0
    unanswerable = {**item, "answerable": False}
    assert hit_at_k(chunks, unanswerable, 4) is None
    assert recall_at_k(chunks, unanswerable, 4) is None
    assert aggregate([
        {"mrr": reciprocal_rank(chunks, item)},
        {"mrr": reciprocal_rank([], item)},
        {"mrr": reciprocal_rank(chunks, unanswerable)},
    ]) == {"mrr": 0.25}


def test_judge_json_is_parsed_with_fences() -> None:
    """Parse fenced JSON even when the model adds introductory text."""

    fence = chr(96) * 3
    answer = f'Result:\n{fence}json\n{{"score": 1, "reason": "Supported."}}\n{fence}'
    assert parse_judgement(answer) == {"score": 1, "reason": "Supported."}
    with pytest.raises(ValueError):
        parse_judgement('{"score": 2, "reason": "Invalid."}')


async def test_correctness_judge_uses_explicit_key_facts() -> None:
    """Send the key-facts checklist together with the reference and answer."""

    settings = get_settings().model_copy(update={
        "groq_base_url": "https://groq.test/openai/v1",
        "groq_api_key": SecretStr("test-key"),
    })

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "ALL key_facts" in payload["messages"][0]["content"]
        assert json.loads(payload["messages"][1]["content"]) == {
            "question": "Hotel limit?", "reference_answer": "PKR 15,000 with pre-approval.",
            "system_answer": "PKR 15,000.", "key_facts": ["PKR 15,000", "pre-approval"],
        }
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"score": 0, "reason": "Missing approval."}'}}]
        })

    async with JudgeClient(settings, transport=httpx.MockTransport(respond)) as judge:
        score = await judge.correctness(
            "Hotel limit?", "PKR 15,000 with pre-approval.", "PKR 15,000.",
            key_facts=["PKR 15,000", "pre-approval"],
        )
    assert score == {"score": 0, "reason": "Missing approval."}


@pytest.mark.parametrize(("header", "expected"), [("2.5", 2.5), (None, 10)])
async def test_disabled_fallback_propagates_groq_delay(header: str | None, expected: float) -> None:
    """Return retry timing to the evaluation runner without sending an Ollama request."""

    settings = get_settings().model_copy(update={
        "groq_base_url": "https://groq.test/openai/v1",
        "ollama_base_url": "http://ollama.test",
        "groq_api_key": SecretStr("test-key"),
        "llm_fallback_enabled": False,
    })
    hosts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(429, headers={"Retry-After": header} if header else {})

    chat = ChatClient(settings, transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RateLimitedError) as raised:
            await chat.complete([{"role": "user", "content": "Leave?"}], 10, 0)
    finally:
        await chat.aclose()
    assert raised.value.retry_after_seconds == expected
    assert hosts == ["groq.test"]
