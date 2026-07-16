"""Consistent error envelope for every error response (blueprint §10.4).

One shape for all errors — HTTP errors, request validation failures, and
unhandled exceptions:

    {
      "error": {
        "code": "validation_error",
        "message": "Request validation failed.",
        "field_errors": [
          {"field": "body.name", "code": "missing", "message": "Field required"}
        ],
        "correlation_id": "...",
        "details": null
      }
    }

``code`` values come from the registry below and only grow; unhandled
exceptions never leak internals into ``message``. ``details`` carries
optional structured context for codes that have it (for example
``dependency_unavailable`` includes the failing readiness checks).
"""

from enum import StrEnum

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import REQUEST_ID_HEADER, get_request_id

_logger = structlog.get_logger("app.errors")


class ErrorCode(StrEnum):
    """Machine-readable error code registry (append-only)."""

    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    HTTP_ERROR = "http_error"
    INTERNAL_ERROR = "internal_error"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    # M2A (ADR-010): browser authentication contract.
    AUTHENTICATION_REQUIRED = "authentication_required"
    INVALID_CREDENTIALS = "invalid_credentials"
    CSRF_REJECTED = "csrf_rejected"


_STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
}


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    field_errors: list[FieldError] = []
    correlation_id: str | None
    # Optional machine-readable context for codes that carry structured
    # information (e.g. dependency_unavailable readiness checks). Null for
    # errors that have none.
    details: dict[str, object] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    field_errors: list[FieldError] | None = None,
    details: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build an ADR-008 envelope response (used by handlers and endpoints)."""
    # The contextvar covers the normal path; the scope-state fallback covers
    # unhandled exceptions, where the correlation middleware has already
    # unwound by the time the outermost error handler runs.
    correlation_id = get_request_id() or getattr(request.state, "request_id", None)
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            field_errors=field_errors or [],
            correlation_id=correlation_id,
            details=details,
        )
    )
    response_headers = dict(headers) if headers else {}
    if correlation_id:
        response_headers[REQUEST_ID_HEADER] = correlation_id
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers=response_headers or None,
    )


class ApiError(Exception):
    """Domain-raisable error rendered as an ADR-008 envelope (M2A).

    Application services raise these to express business/security outcomes
    (invalid credentials, missing authentication, rejected CSRF) without
    knowing anything about HTTP responses; the handler below is the single
    translation point. ``headers`` lets an error carry response headers —
    the session-cookie deletion on authentication failure is the first use.
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101 - handler registration contract
    return error_response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - handler registration contract
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.HTTP_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
    return error_response(request, exc.status_code, code, message)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - handler registration contract
    field_errors = [
        FieldError(
            field=".".join(str(part) for part in error["loc"]),
            code=str(error["type"]),
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]
    return error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_ERROR,
        "Request validation failed.",
        field_errors,
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    _logger.exception("unhandled_exception", exc_info=exc)
    return error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INTERNAL_ERROR,
        "An internal error occurred.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
