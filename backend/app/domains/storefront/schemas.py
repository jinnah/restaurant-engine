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
from typing import Literal

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


class PublishRequest(BaseModel):
    """Publish the current draft (approved ruling D-3).

    ``expected_lock_version`` is required: an owner approves *content*,
    not a row — a draft that changed since they read it is a 409 carrying
    the current value, exactly like restore's guard, never a silent
    publication of someone else's unreviewed edit.
    """

    model_config = ConfigDict(extra="forbid")

    expected_lock_version: int = Field(ge=0)


class RestoreRequest(BaseModel):
    """Restore an archived version into the current draft (ADR-020 §4)."""

    model_config = ConfigDict(extra="forbid")

    expected_lock_version: int = Field(ge=0)


class VersionSummary(BaseModel):
    """One owner-facing history row: the current published version or an
    archived one — never the draft (§4)."""

    id: uuid.UUID
    version_number: int
    state: Literal["published", "archived"]
    design_variant: DesignVariant
    schema_version: int
    published_at: datetime
    published_by_user_id: uuid.UUID
    source_version_id: uuid.UUID | None
    created_at: datetime


class VersionPage(BaseModel):
    """One bounded history page (limit/offset, ``version_number DESC``)."""

    items: list[VersionSummary]
    total: int
    limit: int
    offset: int


class VersionDetail(VersionSummary):
    """One history row with its full composition (restore-confirmation
    inspection). The draft is never readable here — its only read surface
    is the overview."""

    config: StorefrontConfig


class DesignAssignment(BaseModel):
    """Platform command: assign the draft's structural design variant.

    The registry enum publishes the closed set in the contract, so an
    unregistered variant is a 422 before the service runs. There is no
    ``lock_version`` field: the command changes only the platform-owned
    variant and is serialized by the Business row lock (ADR-020 §6).
    """

    model_config = ConfigDict(extra="forbid")

    design_variant: DesignVariant


class DesignAssignmentResult(BaseModel):
    """Bounded acknowledgment for the platform design command.

    Deliberately not a draft view: the §7 matrix denies platform
    administrators every storefront config read, so the response carries
    variant facts only. ``previous_variant: null`` marks the first-draft
    creation path (§5.7), mirroring the audit detail.
    """

    design_variant: DesignVariant
    previous_variant: DesignVariant | None
