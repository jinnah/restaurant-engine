"""Public Business resolution from the request Host (M2C, ADR-013).

The single sanctioned tenant-unscoped read (docs/04 exception 1): the Host
establishes which Business a public request is for. Resolution is
deterministic and fails closed — a Host that is missing, malformed, an IP
literal, off-apex, a deep subdomain, a reserved label, a badly shaped slug,
or an inactive/unknown Business all raise the **same** neutral
``ResourceNotFoundError`` (404). No client header, query parameter, cookie,
or forwarded header can select a Business — only the request Host.

The resolved value is an explicit, request-scoped ``ResolvedBusiness`` DTO
(the same shape as the identity ``ActorContext``): it is not a persistent
``tenant_id`` and not an ambient/global ``TenantContext`` (ADR-012 defers
those). It carries no authorization — a resolved public Business grants no
member or platform access.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ResourceNotFoundError
from app.core.hosts import normalize_host, sole_host_header
from app.core.settings import Settings
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.models import Business
from app.domains.businesses.slugs import is_reserved, is_slug_shaped


@dataclass(frozen=True)
class ResolvedBusiness:
    """The active Business a public request resolved to (request-scoped)."""

    business_id: uuid.UUID
    slug: str
    name: str
    timezone: str
    currency: str


def candidate_slug(host_header: str | None, base_labels: tuple[str, ...]) -> str | None:
    """The subdomain label of ``host_header`` directly under the base domain.

    ``None`` unless the Host is a valid DNS name that is exactly one label
    above ``base_labels`` (an IP literal, the apex itself, or a deeper
    subdomain never yields a candidate).
    """
    normalized = normalize_host(host_header)
    if normalized is None or normalized.is_ip:
        return None
    labels = normalized.labels
    if len(labels) != len(base_labels) + 1:
        return None
    if labels[1:] != base_labels:
        return None
    return labels[0]


def resolve_active_by_slug(db: Session, slug: str) -> Business | None:
    """The single active Business with this canonical slug, or ``None``.

    One indexed lookup constrained by slug **and** active status; there is no
    state-dependent follow-up query (ADR-013 neutral-failure guarantee).
    """
    return db.execute(
        select(Business).where(
            Business.slug == slug,
            Business.status == BusinessStatus.ACTIVE.value,
        )
    ).scalar_one_or_none()


def resolve_public_business(
    request: Request, db: Annotated[Session, Depends(get_session)]
) -> ResolvedBusiness:
    """FastAPI dependency: resolve the active Business from the request Host.

    Every failure mode raises the identical neutral ``ResourceNotFoundError``
    so unknown, provisioning, suspended, closed, reserved, off-apex, and
    malformed inputs are indistinguishable at the public contract level.
    """
    settings: Settings = request.app.state.settings
    # Same fail-closed extraction as the global guard (ADR-013): zero or
    # multiple Host header values never resolve — no first-header selection.
    host_header = sole_host_header(request.scope["headers"])
    slug = candidate_slug(host_header, settings.platform_base_domain_labels)
    if slug is None or is_reserved(slug) or not is_slug_shaped(slug):
        raise ResourceNotFoundError()
    business = resolve_active_by_slug(db, slug)
    if business is None:
        raise ResourceNotFoundError()
    return ResolvedBusiness(
        business_id=business.id,
        slug=business.slug,
        name=business.name,
        timezone=business.timezone,
        currency=business.currency,
    )
