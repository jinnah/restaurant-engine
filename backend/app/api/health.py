"""Liveness and readiness probes.

Root-mounted infrastructure endpoints, deliberately outside `/api/v1`
(they are probe contracts for process supervisors and load balancers, not
versioned product API). Liveness never touches dependencies, so a database
outage can not cause restart loops; readiness reports dependency health
(database check arrives with the database core).
"""

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.core.database import check_database

health_router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["alive"]


class CheckResult(BaseModel):
    status: Literal["up", "down"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckResult]


@health_router.get("/health/live")
def health_live() -> LivenessResponse:
    """Report that the process is up and able to serve HTTP."""
    return LivenessResponse(status="alive")


@health_router.get(
    "/health/ready",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def health_ready(request: Request, response: Response) -> ReadinessResponse:
    """Report whether essential dependencies are reachable.

    The check is deliberately cheap (bounded-timeout SELECT 1). The process
    starts even when the database is down and reports 503 here until it
    recovers — readiness gates traffic, liveness gates restarts.
    """
    engine: Engine = request.app.state.engine
    database_up = check_database(engine)
    if not database_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if database_up else "not_ready",
        checks={"database": CheckResult(status="up" if database_up else "down")},
    )
