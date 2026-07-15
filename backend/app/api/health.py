"""Liveness and readiness probes.

Root-mounted infrastructure endpoints, deliberately outside `/api/v1`
(they are probe contracts for process supervisors and load balancers, not
versioned product API). Liveness never touches dependencies, so a database
outage can not cause restart loops; readiness reports dependency health
(database check arrives with the database core).
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

health_router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["alive"]


@health_router.get("/health/live")
def health_live() -> LivenessResponse:
    """Report that the process is up and able to serve HTTP."""
    return LivenessResponse(status="alive")
