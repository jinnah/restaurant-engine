"""Request correlation IDs.

Every HTTP request gets a correlation ID: a syntactically safe inbound
``X-Request-ID`` is honored (so a future reverse proxy can correlate its own
logs), anything else is replaced with a generated UUID. The ID is exposed via
a contextvar for logging and error envelopes, and echoed on every response.
"""

import re
import uuid
from contextvars import ContextVar

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"

# Strict allowlist: prevents header-based log injection and unbounded values.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Correlation ID of the request being handled, if any."""
    return _request_id_var.get()


def _resolve_request_id(inbound: str | None) -> str:
    if inbound is not None and _SAFE_REQUEST_ID.match(inbound):
        return inbound
    return str(uuid.uuid4())


class CorrelationIdMiddleware:
    """Pure ASGI middleware: resolve, bind, and echo the correlation ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        token = _request_id_var.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id_var.reset(token)
