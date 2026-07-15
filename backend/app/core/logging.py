"""Structured logging (blueprint §16.1).

JSON logs in production, readable console logs in development and test.
Every request is logged once on completion with method, route template,
status, and duration; the correlation ID is merged from contextvars by the
correlation middleware. No secrets, tokens, or unnecessary customer data are
ever logged.
"""

import logging
import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.correlation import get_request_id
from app.core.settings import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog once per process from validated settings."""

    def add_static_fields(
        _logger: object, _method: str, event_dict: structlog.typing.EventDict
    ) -> structlog.typing.EventDict:
        event_dict.setdefault("service", "restaurant-engine-api")
        event_dict.setdefault("environment", settings.app_env.value)
        return event_dict

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_static_fields,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.is_production:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level]
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestLoggingMiddleware:
    """Log one structured event per completed HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._logger = structlog.get_logger("app.request")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            route = scope.get("route")
            self._logger.info(
                "request",
                # Explicit on the canonical request event (other log calls
                # get it merged from contextvars by the correlation layer).
                request_id=get_request_id(),
                method=scope["method"],
                # Route template (e.g. /api/v1/items/{id}) keeps cardinality
                # bounded; unmatched paths (404) fall back to the raw path.
                route=getattr(route, "path_format", None) or scope["path"],
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
