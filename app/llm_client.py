"""Provide async embedding and OpenAI-compatible chat clients."""

import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import aclosing
from dataclasses import dataclass
from math import isfinite
from typing import Self, TypedDict, cast

import httpx
from starlette.requests import Request
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from app.config import Settings
from app.errors import ExternalServiceError

logger = logging.getLogger(__name__)
_CHAT_FAILURES = (
    httpx.HTTPError, httpx.InvalidURL, ValueError, TypeError, KeyError, IndexError, AttributeError,
)


class EmbeddingClient:
    """Embed batches over a shared HTTP connection pool."""

    def __init__(self, settings: Settings) -> None:
        """Configure the Ollama endpoint and request timeout."""

        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=settings.http_timeout_seconds
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings in input order, retrying transient request failures."""

        vectors: list[list[float]] = []
        batch_size = self._settings.embedding_batch_size
        try:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                response = await self._request_embeddings(batch)
                vectors.extend(self._validate_vectors(response.json(), len(batch)))
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, OverflowError) as exc:
            raise ExternalServiceError("Embedding service unavailable") from exc
        return vectors

    async def check_health(self) -> bool:
        """Check whether Ollama responds successfully to its tags endpoint."""

        try:
            response = await self._client.get("/api/tags")
            return response.is_success
        except (httpx.HTTPError, httpx.InvalidURL):
            return False

    async def aclose(self) -> None:
        """Close the shared HTTP client."""

        await self._client.aclose()

    async def _request_embeddings(self, batch: list[str]) -> httpx.Response:
        retry = AsyncRetrying(
            stop=stop_after_attempt(self._settings.http_max_retries),
            wait=wait_exponential(),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )
        return await retry(self._post_batch, batch)

    async def _post_batch(self, batch: list[str]) -> httpx.Response:
        response = await self._client.post(
            "/api/embed", json={"model": self._settings.embed_model, "input": batch}
        )
        return response.raise_for_status()

    def _validate_vectors(self, payload: object, expected_count: int) -> list[list[float]]:
        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != expected_count:
            raise ValueError("Unexpected embedding count")
        for vector in vectors:
            if (
                not isinstance(vector, list)
                or len(vector) != self._settings.embed_dimensions
                or any(type(value) not in (float, int) or not isfinite(value) for value in vector)
            ):
                raise ValueError("Invalid embedding vector")
        return [[float(value) for value in vector] for vector in vectors]


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, httpx.TransportError) or (
        isinstance(exc, httpx.HTTPStatusError) and 500 <= exc.response.status_code < 600
    )


def get_embedding_client(request: Request) -> EmbeddingClient:
    """Return the client created for the current application lifespan."""

    return cast(EmbeddingClient, request.app.state.embedding_client)


class Message(TypedDict):
    """Represent a text message in the OpenAI chat format."""

    role: str
    content: str


@dataclass(frozen=True)
class ChatResult:
    """Store the generated text, chosen provider, and token counts."""

    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class ChatStream(AsyncIterator[str]):
    """Iterate over text deltas and expose the result after consumption."""

    def __init__(self, produce: Callable[[Self], AsyncGenerator[str, None]]) -> None:
        """Create a separate stream and result slot for this request."""

        self.result: ChatResult | None = None
        self._iterator = produce(self)

    def __aiter__(self) -> Self:
        """Return this request's iterator."""

        return self

    async def __anext__(self) -> str:
        """Return the next delta when it becomes available."""

        return await anext(self._iterator)

    async def aclose(self) -> None:
        """Release the response on early exit."""

        await self._iterator.aclose()


class _InterruptedChatStream(Exception):
    """Indicate a stream that stopped after emitting part of an answer."""


class ChatClient:
    """Use Groq chat completions with an Ollama fallback."""

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        """Create one HTTP connection pool for both chat providers."""

        self._settings = settings
        self._client = httpx.AsyncClient(
            timeout=settings.http_timeout_seconds, transport=transport
        )

    async def complete(
        self, messages: list[Message], max_tokens: int, temperature: float
    ) -> ChatResult:
        """Return a completion from the first available provider."""

        for provider, model in self._providers():
            try:
                response = await self._send(
                    provider, self._payload(model, messages, max_tokens, temperature)
                )
                payload = response.json()
                text = _completion_text(payload)
                return self._result(text, provider, model, messages, payload.get("usage"))
            except _CHAT_FAILURES as exc:
                logger.warning("Chat provider %s failed (%s)", provider, type(exc).__name__)
        raise ExternalServiceError("Language model unavailable")

    def stream(
        self, messages: list[Message], max_tokens: int, temperature: float
    ) -> ChatStream:
        """Return an iterator over deltas with final usage on its result field."""

        return ChatStream(
            lambda stream: self._stream(stream, messages, max_tokens, temperature)
        )

    async def classify_injection(self, text: str) -> float | None:
        """Return an optional Groq Prompt Guard probability."""

        try:
            response = await self._post(
                "groq",
                self._payload(
                    self._settings.guard_model, [{"role": "user", "content": text}], 10, 0.0
                ),
            )
            value = _completion_text(response.json()).strip().upper()
            if value in {"MALICIOUS", "JAILBREAK", "INJECTION", "LABEL_1"}:
                return 1.0
            if value in {"BENIGN", "LABEL_0"}:
                return 0.0
            probability = float(value)
            return probability if 0.0 <= probability <= 1.0 else None
        except Exception:
            return None

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""

        await self._client.aclose()

    def _providers(self) -> tuple[tuple[str, str], ...]:
        return (
            ("groq", self._settings.llm_model),
            ("ollama", self._settings.fallback_llm_model),
        )

    @staticmethod
    def _payload(
        model: str, messages: list[Message], max_tokens: int, temperature: float
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"
        return payload

    def _retrying(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self._settings.http_max_retries),
            wait=wait_exponential(),
            retry=retry_if_exception(_is_transient),
            reraise=True,
        )

    async def _send(self, provider: str, payload: dict[str, object]) -> httpx.Response:
        return await self._retrying()(self._post, provider, payload)

    async def _post(
        self, provider: str, payload: dict[str, object], *, stream: bool = False
    ) -> httpx.Response:
        if provider == "groq":
            base = self._settings.groq_base_url
            headers = {"Authorization": f"Bearer {self._settings.groq_api_key.get_secret_value()}"}
        else:
            base = f"{self._settings.ollama_base_url.rstrip('/')}/v1"
            headers = {}
        url = f"{base.rstrip('/')}/chat/completions"
        for attempt in range(2):
            request = self._client.build_request("POST", url, json=payload, headers=headers)
            response = await self._client.send(request, stream=stream)
            if response.is_success:
                return response
            try:
                if (
                    attempt == 0 and provider == "groq" and response.status_code == 400
                    and "reasoning_effort" in payload
                ):
                    body = (await response.aread()).lower()
                    if b"reasoning_effort" in body or b"unknown parameter" in body:
                        payload.pop("reasoning_effort")
                        continue
                response.raise_for_status()
            finally:
                await response.aclose()
        raise ValueError("Unsupported chat request")

    async def _stream(
        self, stream: ChatStream, messages: list[Message], max_tokens: int, temperature: float
    ) -> AsyncGenerator[str, None]:
        for provider, model in self._providers():
            payload = self._payload(model, messages, max_tokens, temperature)
            payload["stream"] = True
            if provider == "groq":
                payload["stream_options"] = {"include_usage": True}
            try:
                async for attempt in self._retrying():
                    with attempt:
                        async with aclosing(
                            self._read_stream(stream, provider, model, payload, messages)
                        ) as deltas:
                            async for delta in deltas:
                                yield delta
                        return
            except _InterruptedChatStream:
                logger.warning("Chat stream from %s ended before completion", provider)
                break
            except _CHAT_FAILURES as exc:
                logger.warning("Chat stream provider %s failed (%s)", provider, type(exc).__name__)
        raise ExternalServiceError("Language model unavailable")

    async def _read_stream(
        self, stream: ChatStream, provider: str, model: str, payload: dict[str, object],
        messages: list[Message],
    ) -> AsyncGenerator[str, None]:
        parts: list[str] = []
        usage = None
        finished = False
        response = await self._post(provider, payload, stream=True)
        try:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    finished = True
                    break
                event = json.loads(data)
                usage = event.get("usage") or usage
                for choice in event.get("choices") or []:
                    finished |= choice.get("finish_reason") is not None
                    delta = choice.get("delta", {}).get("content")
                    if isinstance(delta, str) and delta:
                        parts.append(delta)
                        yield delta
            if not finished or not "".join(parts).strip():
                raise ValueError("Incomplete chat stream")
        except _CHAT_FAILURES as exc:
            if parts:
                # Once text has been emitted, a retry would splice together two answers.
                raise _InterruptedChatStream from exc
            raise
        finally:
            await response.aclose()
        stream.result = self._result("".join(parts), provider, model, messages, usage)

    @staticmethod
    def _result(
        text: str, provider: str, model: str, messages: list[Message], usage: object
    ) -> ChatResult:
        counts = usage if isinstance(usage, dict) else {}
        prompt = counts.get("prompt_tokens")
        completion = counts.get("completion_tokens")
        if not isinstance(prompt, int):
            prompt = round(1.3 * sum(len(message["content"].split()) for message in messages))
        if not isinstance(completion, int):
            completion = round(1.3 * len(text.split()))
        logger.info("Chat answered via %s", provider)
        return ChatResult(text, provider, model, prompt, completion)


def _completion_text(payload: object) -> str:
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                text = message.get("content")
                if isinstance(text, str) and text.strip():
                    return text
    raise ValueError("Empty or malformed chat completion")


def get_chat_client(request: Request) -> ChatClient:
    """Return the chat client owned by the current application lifespan."""

    return cast(ChatClient, request.app.state.chat_client)
