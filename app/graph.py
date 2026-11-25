"""Run guarded question answering as an async LangGraph workflow."""

from collections.abc import Awaitable, Callable
from contextlib import aclosing
from functools import lru_cache, wraps
from time import perf_counter
from typing import Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ExternalServiceError
from app.generation import NOT_IN_DOCUMENTS, REFUSAL_MESSAGES, build_messages
from app.guardrails import check_answer, check_injection_model, check_question, validate_citations
from app.llm_client import ChatClient, EmbeddingClient, Message
from app.retrieval import RetrievedChunk, count_owner_documents, retrieve


class State(TypedDict, total=False):
    """Carry the question, retrieved context, and answer through the graph."""

    question: str
    owner_id: str
    top_k: int | None
    chunks: list[RetrievedChunk]
    messages: list[Message]
    answer: str
    citations: list[str]
    refused: bool
    refusal_reason: str | None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    timings_ms: dict[str, float]
    stream: bool


class _Dependencies(TypedDict):
    session: AsyncSession
    embedder: EmbeddingClient
    chat_client: ChatClient
    settings: Settings


_Node = Callable[[State, RunnableConfig], Awaitable[State]]


def _dependencies(config: RunnableConfig) -> _Dependencies:
    return cast(_Dependencies, config["configurable"])


def _timed(node: _Node) -> _Node:
    @wraps(node)
    async def run(state: State, config: RunnableConfig) -> State:
        name = node.__name__.removeprefix("_")
        get_stream_writer()({"type": "stage", "stage": name})
        timings = state.get("timings_ms")
        if timings is None:
            timings = {}
        started = perf_counter()
        try:
            updates = await node(state, config)
        finally:
            timings[name] = round((perf_counter() - started) * 1000, 2)
        return {**updates, "timings_ms": timings}

    return run


@_timed
async def _guard_input(state: State, config: RunnableConfig) -> State:
    deps = _dependencies(config)
    result = check_question(state["question"], deps["settings"])
    if not result.ok:
        return {"refusal_reason": result.reason}
    if await check_injection_model(state["question"], deps["chat_client"]):
        return {"refusal_reason": "prompt_injection"}
    return {}


@_timed
async def _check_corpus(state: State, config: RunnableConfig) -> State:
    if not await count_owner_documents(_dependencies(config)["session"], state["owner_id"]):
        return {"refusal_reason": "no_documents"}
    return {}


@_timed
async def _retrieve(state: State, config: RunnableConfig) -> State:
    deps = _dependencies(config)
    chunks = await retrieve(
        deps["session"], state["owner_id"], state["question"], deps["embedder"],
        deps["settings"], state.get("top_k"),
    )
    return {"chunks": chunks}


@_timed
async def _check_relevance(state: State, config: RunnableConfig) -> State:
    chunks = state["chunks"]
    threshold = _dependencies(config)["settings"].min_similarity
    if not chunks or max(chunk.similarity for chunk in chunks) < threshold:
        return {"refusal_reason": "low_relevance"}
    return {}


@_timed
async def _generate(state: State, config: RunnableConfig) -> State:
    deps = _dependencies(config)
    chat = deps["chat_client"]
    settings = deps["settings"]
    messages = build_messages(state["question"], state["chunks"])
    if state.get("stream"):
        writer = get_stream_writer()
        async with aclosing(chat.stream(messages, settings.llm_max_tokens, settings.llm_temperature)) as output:
            async for delta in output:
                writer({"type": "token", "text": delta})
            result = output.result
        if result is None:
            raise ExternalServiceError("Language model unavailable")
    else:
        result = await chat.complete(messages, settings.llm_max_tokens, settings.llm_temperature)
    answer = result.text.strip()
    return {
        "messages": messages,
        "answer": answer,
        "provider": result.provider,
        "model": result.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "refusal_reason": "not_in_documents" if answer == NOT_IN_DOCUMENTS else None,
    }


@_timed
async def _validate_output(state: State, config: RunnableConfig) -> State:
    result = check_answer(state["answer"])
    if not result.ok:
        return {"refusal_reason": result.reason}
    answer, valid_ids, _ = validate_citations(state["answer"], state["chunks"])
    if not valid_ids:
        return {"refusal_reason": "ungrounded"}
    return {"answer": answer, "citations": valid_ids}


@_timed
async def _refuse(state: State, config: RunnableConfig) -> State:
    reason = state.get("refusal_reason") or "ungrounded"
    return {"refused": True, "answer": REFUSAL_MESSAGES[reason], "citations": []}


def _continue_or_refuse(state: State) -> Literal["continue", "refuse"]:
    return "refuse" if state.get("refusal_reason") else "continue"


@lru_cache
def build_graph() -> CompiledStateGraph:
    """Compile and cache the stateless question-answering workflow."""

    graph = StateGraph(State)
    stages = {
        "guard_input": _guard_input,
        "check_corpus": _check_corpus,
        "retrieve": _retrieve,
        "check_relevance": _check_relevance,
        "generate": _generate,
        "validate_output": _validate_output,
    }
    for name, run in stages.items():
        graph.add_node(name, run)
    graph.add_node("refuse", _refuse)
    graph.add_edge(START, "guard_input")
    for source, destination in zip(stages, [*list(stages)[1:], END], strict=True):
        graph.add_conditional_edges(
            source, _continue_or_refuse, {"continue": destination, "refuse": "refuse"}
        )
    graph.add_edge("refuse", END)
    return graph.compile()


def draw_graph_mermaid() -> str:
    """Return a Mermaid representation of the compiled workflow."""

    return build_graph().get_graph().draw_mermaid()
