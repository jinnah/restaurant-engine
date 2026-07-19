"""Business-scoped catalog administration endpoints (M3A, ADR-017).

Routers translate only (docs/02): the service enforces capabilities, the
business-row lock, and the lifecycle rules. The tenant comes from the
route path and is validated against the caller's membership inside the
service — nonmembers (including platform admins, who hold no membership)
get 404. Every unsafe route carries the two M2A CSRF layers. Operation
IDs are permanent client contracts (ADR-009).
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.errors import ErrorEnvelope
from app.domains.catalog import service
from app.domains.catalog.schemas import (
    AdminMenu,
    CategoryCreate,
    CategoryReorder,
    CategorySummary,
    CategoryUpdate,
    DeletedResponse,
    ItemAvailabilitySet,
    ItemCreate,
    ItemReorder,
    ItemSummary,
    ItemUpdate,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.dependencies import csrf_protected_actor, current_actor

catalog_admin_router = APIRouter(prefix="/businesses/{business_id}/catalog", tags=["catalog"])

_READ_ENVELOPES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}
_WRITE_ENVELOPES: dict[int | str, dict[str, Any]] = {
    **_READ_ENVELOPES,
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@catalog_admin_router.get(
    "/menu",
    operation_id="catalog_admin_menu_get",
    responses=_READ_ENVELOPES,
)
def catalog_admin_menu_get(
    business_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> AdminMenu:
    """The complete administrative menu tree (hidden entries included)."""
    return service.get_admin_menu(db, actor, business_id)


# --- Categories --------------------------------------------------------------


@catalog_admin_router.post(
    "/categories",
    operation_id="catalog_category_create",
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ENVELOPES,
)
def catalog_category_create(
    business_id: uuid.UUID,
    payload: CategoryCreate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> CategorySummary:
    """Create a category (appended at the end of the menu)."""
    return service.create_category(db, actor, business_id, payload)


@catalog_admin_router.patch(
    "/categories/{category_id}",
    operation_id="catalog_category_update",
    responses=_WRITE_ENVELOPES,
)
def catalog_category_update(
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> CategorySummary:
    """Update a category's name, description, or visibility."""
    return service.update_category(db, actor, business_id, category_id, payload)


@catalog_admin_router.delete(
    "/categories/{category_id}",
    operation_id="catalog_category_delete",
    responses=_WRITE_ENVELOPES,
)
def catalog_category_delete(
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> DeletedResponse:
    """Delete an empty category (non-empty → 409, ruling D7)."""
    service.delete_category(db, actor, business_id, category_id)
    return DeletedResponse()


@catalog_admin_router.post(
    "/categories/reorder",
    operation_id="catalog_categories_reorder",
    responses=_WRITE_ENVELOPES,
)
def catalog_categories_reorder(
    business_id: uuid.UUID,
    payload: CategoryReorder,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminMenu:
    """Full-set category reorder; returns the updated menu tree."""
    return service.reorder_categories(db, actor, business_id, payload)


# --- Items -------------------------------------------------------------------


@catalog_admin_router.post(
    "/categories/{category_id}/items",
    operation_id="catalog_item_create",
    status_code=status.HTTP_201_CREATED,
    responses=_WRITE_ENVELOPES,
)
def catalog_item_create(
    business_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: ItemCreate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> ItemSummary:
    """Create an item (appended at the end of its category)."""
    return service.create_item(db, actor, business_id, category_id, payload)


@catalog_admin_router.get(
    "/items/{item_id}",
    operation_id="catalog_item_get",
    responses=_READ_ENVELOPES,
)
def catalog_item_get(
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(current_actor)],
) -> ItemSummary:
    """Read one item (any member)."""
    return service.get_item(db, actor, business_id, item_id)


@catalog_admin_router.patch(
    "/items/{item_id}",
    operation_id="catalog_item_update",
    responses=_WRITE_ENVELOPES,
)
def catalog_item_update(
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemUpdate,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> ItemSummary:
    """Update an item (name/description/price/hidden/featured/tags/category).

    Availability is deliberately not part of this PATCH — it is the
    separate ``catalog_item_availability_set`` command (ruling D4).
    """
    return service.update_item(db, actor, business_id, item_id, payload)


@catalog_admin_router.delete(
    "/items/{item_id}",
    operation_id="catalog_item_delete",
    responses=_WRITE_ENVELOPES,
)
def catalog_item_delete(
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> DeletedResponse:
    """Delete an item; remaining positions renormalize."""
    service.delete_item(db, actor, business_id, item_id)
    return DeletedResponse()


@catalog_admin_router.post(
    "/items/reorder",
    operation_id="catalog_items_reorder",
    responses=_WRITE_ENVELOPES,
)
def catalog_items_reorder(
    business_id: uuid.UUID,
    payload: ItemReorder,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> AdminMenu:
    """Full-set item reorder within one category; returns the menu tree."""
    return service.reorder_items(db, actor, business_id, payload)


@catalog_admin_router.post(
    "/items/{item_id}/availability",
    operation_id="catalog_item_availability_set",
    responses=_WRITE_ENVELOPES,
)
def catalog_item_availability_set(
    business_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ItemAvailabilitySet,
    db: Annotated[Session, Depends(get_session)],
    actor: Annotated[ActorContext, Depends(csrf_protected_actor)],
) -> ItemSummary:
    """The "sold out today" toggle (staff-reachable, ruling D4)."""
    return service.set_item_availability(db, actor, business_id, item_id, payload)
