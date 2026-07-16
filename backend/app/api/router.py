"""Versioned API composition root.

Domain routers are included here as their milestones deliver them.
The router itself establishes the permanent `/api/v1` mount point
(blueprint §10).
"""

from fastapi import APIRouter

from app.domains.identity.router import auth_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
