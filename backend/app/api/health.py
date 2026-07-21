"""Liveness and readiness probes.

Root-mounted infrastructure endpoints, deliberately outside `/api/v1`
(they are probe contracts for process supervisors and load balancers, not
versioned product API). Liveness never touches dependencies, so a database
outage can not cause restart loops; readiness reports dependency health
(database check arrives with the database core).
"""

from typing import Literal

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.core.database import check_database
from app.core.errors import ErrorCode, ErrorEnvelope, error_response
from app.domains.media.storage import LocalFilesystemStorage

_logger = structlog.get_logger("app.health")


def _check_media_storage(storage: LocalFilesystemStorage) -> bool:
    """Cheap collision-safe write/stat/delete probe (M3C, ADR-017).

    Never iterates the media inventory and never exposes the root path in
    the response — a failure is logged by exception name only.
    """
    try:
        storage.probe()
    except OSError as exc:
        _logger.warning("media_storage_check_failed", error=type(exc).__name__)
        return False
    return True


health_router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class CheckResult(BaseModel):
    status: Literal["up", "down"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    checks: dict[str, CheckResult]


@health_router.get("/health/live", operation_id="health_live")
def health_live() -> LivenessResponse:
    """Report that the process is up and able to serve HTTP."""
    return LivenessResponse(status="alive")


@health_router.get(
    "/health/ready",
    operation_id="health_ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorEnvelope}},
)
def health_ready(request: Request) -> ReadinessResponse | JSONResponse:
    """Report whether essential dependencies are reachable.

    The check is deliberately cheap (bounded-timeout SELECT 1). The process
    starts even when the database is down and reports 503 here until it
    recovers — readiness gates traffic, liveness gates restarts.

    Not-ready is an error state, so it uses the ADR-008 envelope
    (``dependency_unavailable``) with the failing checks preserved in
    ``error.details.checks``.
    """
    engine: Engine = request.app.state.engine
    media_storage: LocalFilesystemStorage = request.app.state.media_storage
    checks = {
        "database": check_database(engine),
        "media_storage": _check_media_storage(media_storage),
    }
    if not all(checks.values()):
        return error_response(
            request,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "Service dependencies are unavailable.",
            details={
                "checks": {name: "up" if healthy else "down" for name, healthy in checks.items()}
            },
        )
    return ReadinessResponse(
        status="ready",
        checks={name: CheckResult(status="up") for name in checks},
    )
