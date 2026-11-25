"""Map question workflows to API responses, validated SSE, and metrics."""

import logging
import traceback
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import asdict
from time import perf_counter
from typing import cast

from langchain_core.runnables import RunnableConfig
from langsmith import tracing_context
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import AskLog, SessionFactory
from app.errors import ExternalServiceError, RagServiceError
from app.graph import State, build_graph
from app.llm_client import ChatClient, EmbeddingClient
from app.repository import insert_ask_log
from app.schemas import AskRequest, AskResponse, CitationOut, ErrorBody, ErrorResponse, RetrievedChunkOut

logger = logging.getLogger(__name__)


class AskService:
    """Run the question workflow with request-scoped dependencies."""

    def __init__(
        self, session: AsyncSession, embedder: EmbeddingClient, chat: ChatClient,
        settings: Settings, owner_id: str, request_id: str,
    ) -> None:
        """Bind the request's services, ownership, and correlation ID."""

        self._owner_id = owner_id
        self._request_id = request_id
        self._config: RunnableConfig = {
            "configurable": {
                "session": session,
                "embedder": embedder,
                "chat_client": chat,
                "settings": settings,
            }
        }

    async def answer(self, request: AskRequest) -> AskResponse:
        """Run the graph once and record the outcome."""

        started = perf_counter()
        state = self._initial_state(request, stream=False)
        error = True
        try:
            with tracing_context(enabled=False):
                state = cast(State, await build_graph().ainvoke(state, self._config))
            response = self._response(state)
            error = False
            return response
        finally:
            await self._log(state, started, error)

    async def stream(self, request: AskRequest) -> AsyncIterator[str]:
        """Stream progress live and release generated text after answer validation."""

        started = perf_counter()
        state = self._initial_state(request, stream=True)
        tokens: list[str] = []
        error: ErrorBody | None = None
        try:
            with tracing_context(enabled=False):
                async with aclosing(build_graph().astream(
                    state, self._config, stream_mode=["custom", "values"]
                )) as events:
                    async for mode, payload in events:
                        if mode == "values":
                            state = payload
                        elif payload["type"] == "stage":
                            yield _event("stage", _StageEvent(stage=payload["stage"]))
                        elif payload["type"] == "token":
                            tokens.append(payload["text"])
            response = self._response(state)
        except RagServiceError as exc:
            error = ErrorBody(code=exc.error_code, message=str(exc), request_id=self._request_id)
        except Exception as exc:
            logger.error(
                "Question stream failed (%s)\n%s",
                type(exc).__name__, "".join(traceback.format_tb(exc.__traceback__)),
            )
            error = ErrorBody(
                code="internal_error", message="An unexpected error occurred.",
                request_id=self._request_id,
            )
        await self._log(state, started, error is not None)
        if error is not None:
            yield _event("error", ErrorResponse(error=error))
            return

        if not response.refused:
            # Release the original deltas only if validation left the text unchanged.
            for token in tokens if "".join(tokens) == response.answer else [response.answer]:
                yield _event("token", _TokenEvent(text=token))
        yield _event("done", response)

    def _initial_state(self, request: AskRequest, *, stream: bool) -> State:
        return {
            "question": request.question,
            "owner_id": self._owner_id,
            "top_k": request.top_k,
            "timings_ms": {},
            "stream": stream,
        }

    def _response(self, state: State) -> AskResponse:
        chunks = state.get("chunks", [])
        chunk_by_citation = {chunk.citation_id: chunk for chunk in chunks}
        cited = state.get("citations", [])
        citations: list[CitationOut] = []
        for citation in cited:
            chunk = chunk_by_citation[citation]
            citations.append(CitationOut(
                id=citation, chunk_id=chunk.chunk_id, document_id=chunk.document_id,
                filename=chunk.filename, page=chunk.page, section=chunk.section,
            ))
        return AskResponse(
            answer=state["answer"],
            refused=state.get("refused", False),
            refusal_reason=state.get("refusal_reason"),
            citations=citations,
            chunks=[
                RetrievedChunkOut(**asdict(chunk), cited=chunk.citation_id in cited)
                for chunk in chunks
            ],
            retrieved_count=len(chunks),
            provider=state.get("provider"),
            model=state.get("model"),
            timings_ms=state["timings_ms"],
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            request_id=self._request_id,
        )

    async def _log(self, state: State, started: float, error: bool) -> None:
        entry = AskLog(
            owner_id=self._owner_id,
            request_id=self._request_id,
            question_chars=len(state["question"]),
            latency_ms=round((perf_counter() - started) * 1000, 2),
            provider=state.get("provider"),
            model=state.get("model"),
            refused=state.get("refused", False),
            refusal_reason=state.get("refusal_reason"),
            error=error,
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            retrieved_count=len(state.get("chunks", [])),
            timings_ms=state["timings_ms"],
        )
        try:
            async with SessionFactory() as session:
                await insert_ask_log(session, entry)
        except ExternalServiceError:
            logger.warning("Could not persist question metrics")


class _StageEvent(BaseModel):
    stage: str


class _TokenEvent(BaseModel):
    text: str


def _event(name: str, data: BaseModel) -> str:
    return f"event: {name}\ndata: {data.model_dump_json()}\n\n"
