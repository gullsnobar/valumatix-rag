"""Configure secret-safe structured request logging with request IDs and latency."""

import logging
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from logging.config import dictConfig
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class RequestIdFilter(logging.Filter):
    """Add the active request ID to records processed by the log handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Read the ID from the context for the current task."""

        record.request_id = request_id_var.get()
        return True


def configure_logging() -> None:
    """Configure request-aware logging and suppress duplicate access logs."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "request": {
                    "format": "%(asctime)s %(levelname)s request_id=%(request_id)s %(message)s"
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "filters": ["request_id"],
                    "formatter": "request",
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
            "loggers": {
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "uvicorn.access": {"level": "WARNING"},
            },
        }
    )


class RequestIdMiddleware:
    """Assign a request ID and log the latency and result of each HTTP request."""

    def __init__(
        self, app: ASGIApp, on_error: Callable[[Request, Exception], Awaitable[Response]]
    ) -> None:
        """Wrap the app and keep its handler for unhandled request failures."""

        self.app = app
        self.on_error = on_error

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Run an HTTP request in its own logging context."""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_id = Headers(scope=scope).get("x-request-id", "")
        request_id = supplied_id if _REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        start = perf_counter()
        status = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            if response_started:
                raise
            response = await self.on_error(Request(scope), exc)
            await response(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "%s %r %d %.1f ms",
                scope["method"],
                scope["path"],
                status,
                (perf_counter() - start) * 1000,
            )
            request_id_var.reset(token)
