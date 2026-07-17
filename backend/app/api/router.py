"""Versioned API composition root.

Domain routers are included here as their milestones deliver them, plus the
application-layer composition routers (e.g. the enriched session view) that
orchestrate more than one domain. The router establishes the permanent
`/api/v1` mount point (blueprint §10).
"""

from fastapi import APIRouter

from app.api.session_router import session_router
from app.domains.identity.router import auth_router
from app.domains.tenants.router import restaurant_router
from app.domains.tenants.router_platform import platform_router

api_v1_router = APIRouter()
# Identity credential operations (login/logout).
api_v1_router.include_router(auth_router)
# Application composition: the enriched GET /auth/session view.
api_v1_router.include_router(session_router)
# Tenants: platform lifecycle management + the restaurant-scoped member read.
api_v1_router.include_router(platform_router)
api_v1_router.include_router(restaurant_router)
