"""Versioned API composition root.

Domain routers are included here as their milestones deliver them
(Milestone 2 onward). The router itself establishes the permanent `/api/v1`
mount point from the start (blueprint §10).
"""

from fastapi import APIRouter

api_v1_router = APIRouter()
