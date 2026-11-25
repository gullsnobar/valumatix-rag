"""Detect instruction overrides and check generated answers and citations."""

import re
from dataclasses import dataclass

from app.config import Settings
from app.llm_client import ChatClient
from app.retrieval import RetrievedChunk

SYSTEM_PROMPT_CANARY = "TRNWK-CANARY-4f9b2c"
INJECTION_PATTERNS = [
    # Requests to override existing instructions.
    re.compile(
        r"\b(?:ignore|disregard|forget|override)\b.{0,50}\b(?:previous|prior|above|earlier|system)"
        r"\b.{0,24}\b(?:instructions?|rules?|prompts?)\b",
        re.I | re.S,
    ),
    # Requests to disclose internal model instructions.
    re.compile(
        r"\b(?:reveal|print|show|repeat|disclose|display|output)\b.{0,60}"
        r"\b(?:system|developer)\s+(?:prompt|instructions?)\b",
        re.I | re.S,
    ),
    # Role changes, known jailbreak personas, and removal of constraints.
    re.compile(
        r"\b(?:you are now|act as|pretend to be)\b.{0,45}"
        r"\b(?:unrestricted|uncensored|unfiltered|unlimited|rule[- ]free|DAN|jailbroken)\b",
        re.I | re.S,
    ),
    re.compile(r"\b(?:DAN|do anything now|developer mode|jailbreak|no rules)\b", re.I),
    # Encoded instructions that the caller also asks the model to execute.
    re.compile(
        r"(?:\bdecode\b.{0,35}\bbase\s*64\b|\bbase\s*64\b.{0,35}\bdecode\b)"
        r".{0,120}\b(?:follow|execute|obey|run|apply)\b",
        re.I | re.S,
    ),
]
_CITATION = re.compile(r"\[(C[0-9]+)\]")
_API_KEY = re.compile(
    r"\b(?:gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{16,})",
    re.I,
)
_QUOTED_INSTRUCTIONS = re.compile(r"""["“][^"”]{4,}["”]|['‘][^'’]{4,}['’]|\x60{3}""", re.S)


@dataclass(frozen=True)
class GuardResult:
    """Report whether a safety check passed and why it refused if it failed."""

    ok: bool
    reason: str | None = None


def check_question(question: str, settings: Settings) -> GuardResult:
    """Check that a question is present, bounded, and free of override patterns."""

    if not question.strip():
        return GuardResult(False, "empty_question")
    if len(question) > settings.max_question_chars:
        return GuardResult(False, "question_too_long")
    if any(pattern.search(question) for pattern in INJECTION_PATTERNS):
        return GuardResult(False, "prompt_injection")
    return GuardResult(True)


async def check_injection_model(question: str, chat_client: ChatClient) -> bool:
    """Flag an injection when the optional classifier reports high enough confidence."""

    probability = await chat_client.classify_injection(question)
    return probability is not None and probability >= 0.5


def check_answer(answer: str) -> GuardResult:
    """Withhold answers containing a canary, credential, or quoted internal prompt."""

    if (
        SYSTEM_PROMPT_CANARY.casefold() in answer.casefold()
        or _API_KEY.search(answer)
        or ("system prompt" in answer.casefold() and _QUOTED_INSTRUCTIONS.search(answer))
    ):
        return GuardResult(False, "output_blocked")
    return GuardResult(True)


def extract_citations(answer: str) -> list[str]:
    """List distinct citation IDs in order of first appearance."""

    return list(dict.fromkeys(_CITATION.findall(answer)))


def validate_citations(
    answer: str, retrieved: list[RetrievedChunk]
) -> tuple[str, list[str], list[str]]:
    """Remove markers for unavailable sources and return valid and invalid IDs."""

    available = {chunk.citation_id for chunk in retrieved}
    cited = extract_citations(answer)
    valid = [citation for citation in cited if citation in available]
    invalid = [citation for citation in cited if citation not in available]
    clean_answer = _CITATION.sub(lambda m: m[0] if m[1] in available else "", answer)
    return clean_answer.strip(), valid, invalid
