"""Storefront API schemas (M4B, ADR-020).

Commands are strict (``extra="forbid"``); responses are explicit
projections, never serialized ORM objects. The composition payload *is*
the M4A registry contract (``StorefrontConfig``), so the OpenAPI document
publishes the full typed section registry and the generated client sees
every section shape.

Owner/manager draft commands carry **no** ``design_variant`` field — the
variant is platform-governed (ADR-020 §5.10), so submitting one is a 422
from ``extra="forbid"``, never a silently ignored value.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.storefront.composition import StorefrontConfig
from app.domains.storefront.variants import DesignVariant


class DraftView(BaseModel):
    """The singleton mutable draft.

    The overview is the **only** administrative read representation of the
    draft — history endpoints expose published and archived rows only.
    ``lock_version`` is the optimistic-concurrency token every draft
    mutation must present back (ADR-020 §6).
    """

    config: StorefrontConfig
    design_variant: DesignVariant
    lock_version: int
    schema_version: int
    source_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PublishedSummary(BaseModel):
    """The at-most-one currently published version (metadata only)."""

    id: uuid.UUID
    version_number: int
    design_variant: DesignVariant
    schema_version: int
    published_at: datetime
    published_by_user_id: uuid.UUID


class StorefrontOverview(BaseModel):
    """The administrative storefront state of one business.

    ``draft: null`` (with ``published: null``) is the valid first-use
    absence: storefront reads never create state (ADR-020 §5.1), so a
    business that has never composed anything reads as absent rather than
    404 — on these routes 404 already means "not your business".
    """

    draft: DraftView | None
    published: PublishedSummary | None


class DraftPut(BaseModel):
    """Full-document draft replacement — create or update in one route (D-5).

    ``expected_lock_version`` is the explicit intent representation
    (ADR-020 §5.4): omitted or ``null`` means "I believe no draft exists"
    (create); an integer means "I believe the draft is at exactly this
    version" (update). A guessed ``0`` is therefore an update claim and can
    never silently create or overwrite.
    """

    model_config = ConfigDict(extra="forbid")

    config: StorefrontConfig
    expected_lock_version: int | None = Field(default=None, ge=0)
