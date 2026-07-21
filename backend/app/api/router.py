"""Versioned API composition root.

Domain routers are included here as their milestones deliver them, plus the
application-layer composition routers (e.g. the enriched session view) that
orchestrate more than one domain. The router establishes the permanent
`/api/v1` mount point (blueprint §10).
"""

from fastapi import APIRouter

from app.api.audit_router import audit_business_router, audit_platform_router
from app.api.session_router import session_router
from app.domains.businesses.router import business_router
from app.domains.businesses.router_invitations import invitations_router
from app.domains.businesses.router_onboarding import onboarding_router
from app.domains.businesses.router_platform import platform_router
from app.domains.businesses.router_public import public_router
from app.domains.catalog.router_admin import catalog_admin_router
from app.domains.catalog.router_public import catalog_public_router
from app.domains.identity.router import auth_router
from app.domains.identity.router_recovery import (
    recovery_platform_router,
    recovery_public_router,
)
from app.domains.media.router_admin import media_admin_router

api_v1_router = APIRouter()
# Identity credential operations (login/logout).
api_v1_router.include_router(auth_router)
# Application composition: the enriched GET /auth/session view.
api_v1_router.include_router(session_router)
# Businesses: platform lifecycle management + the business-scoped member read.
api_v1_router.include_router(platform_router)
api_v1_router.include_router(business_router)
# Public, host-resolved storefront surface (M2C); unauthenticated.
api_v1_router.include_router(public_router)
# Recovery (M2D): platform-issued reset tokens + public redemption.
api_v1_router.include_router(recovery_platform_router)
api_v1_router.include_router(recovery_public_router)
# Onboarding (M2D): business-scoped invitation management + public
# redemption. Platform invitation routes live on the platform router.
api_v1_router.include_router(invitations_router)
api_v1_router.include_router(onboarding_router)
# Audit lists (M2D): application composition — authz here, audit stays pure.
api_v1_router.include_router(audit_platform_router)
api_v1_router.include_router(audit_business_router)
# Catalog (M3A): business-scoped menu administration.
api_v1_router.include_router(catalog_admin_router)
# Catalog (M3D): the host-resolved public menu projection; unauthenticated.
api_v1_router.include_router(catalog_public_router)
# Media (M3C): business-scoped image upload/list/get/preview/delete.
api_v1_router.include_router(media_admin_router)
