"""Typed detail schemas for audit events (M2A, approved review item R13).

Every recordable action has exactly one detail schema here (or ``None``).
Call sites can not pass free-form dictionaries: the recorder accepts only
these models, so the set of keys that can ever reach the ``details`` JSONB
column is closed, reviewable, and provably free of secrets
(tests/unit/test_audit_details.py enforces the denylist).

Emails of platform users (owners, staff, admins) are deliberately allowed:
they are operational identifiers needed for security forensics, not
customer data (docs/04 privacy-minimization).
"""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)


class AuditDetails(BaseModel):
    """Base class for all audit detail payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LoginFailedDetails(AuditDetails):
    """Why a login attempt was rejected (never disclosed to the client)."""

    email_normalized: str
    reason: Literal["unknown_email", "invalid_password", "inactive_account"]


class LoginThrottledDetails(AuditDetails):
    """An attempt arrived inside the account's backoff window."""

    email_normalized: str
    failed_login_count: int
    backoff_seconds: int


class PlatformAdminCreatedDetails(AuditDetails):
    """A platform administrator account was created via the bootstrap CLI."""

    email_normalized: str


class BusinessCreatedDetails(AuditDetails):
    """A business was created (starts in provisioning)."""

    slug: str


class BusinessStatusChangedDetails(AuditDetails):
    """A business lifecycle transition (M2B)."""

    previous_status: str
    new_status: str


class InvitationDetails(AuditDetails):
    """A membership invitation was issued, revoked, or accepted (M2D).

    Never the token or its hash — only the invited identity and role.
    """

    email_normalized: str
    role: str


class EntitlementDetails(AuditDetails):
    """A product feature was granted to or revoked from a business (M2D)."""

    feature_key: str


class PasswordResetDetails(AuditDetails):
    """A recovery token was issued or redeemed (M2D).

    Never the token or its hash. The issuing administrator is the event's
    actor; the affected account is the target and its email is recorded
    here (platform-user emails are allowed operational identifiers).
    """

    email_normalized: str


# --- Catalog (M3A, ADR-017) --------------------------------------------------
#
# Bounded values only: normalized names are <= 120 chars; changed_fields is
# a comma-joined, sorted string drawn from a closed field-name set (a plain
# bounded string, so the read-time projection's primitive extractors apply
# unchanged); prices are ints <= MAX_PRICE_MINOR. Free-text descriptions
# never enter audit payloads.


class CatalogCategoryDetails(AuditDetails):
    """A menu category was created or deleted."""

    name: str


class CatalogCategoryUpdatedDetails(AuditDetails):
    """A menu category changed; which fields is the closed-set summary."""

    name: str
    changed_fields: str


class CatalogReorderDetails(AuditDetails):
    """A full-set reorder ran (categories or items); count of rows."""

    count: int


class CatalogItemCreatedDetails(AuditDetails):
    """A menu item was created."""

    name: str
    category_id: str
    price_minor: int


class CatalogItemUpdatedDetails(AuditDetails):
    """A menu item changed.

    ``price_minor_old``/``price_minor_new`` are present exactly when the
    price changed (queryable price history); ``category_id`` is the
    destination exactly when the item moved.
    """

    changed_fields: str
    price_minor_old: int | None = None
    price_minor_new: int | None = None
    category_id: str | None = None


class CatalogItemDeletedDetails(AuditDetails):
    """A menu item was deleted."""

    name: str
    category_id: str


class CatalogItemAvailabilityDetails(AuditDetails):
    """The staff-reachable "sold out today" toggle changed state."""

    availability: Literal["available", "sold_out"]


# --- Modifiers (M3B, ADR-017) -------------------------------------------------
#
# The maximum-selection mode is explicit (D6 correction): never inferred
# from field absence. Mode and availability values are closed-set strings
# so the read-time projection needs no boolean in its value union.
#
# D6 binds field *presence* at both layers: inapplicable optional fields
# are omitted from the stored payload too, not stored as explicit nulls.
# The omission lives in these schemas' own serializer — the shared M2A
# recorder and every earlier detail schema are untouched.


class ModifierAuditDetails(AuditDetails):
    """Base for M3B modifier details: None fields never reach storage."""

    @model_serializer(mode="wrap")
    def _omit_none(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        return {key: value for key, value in handler(self).items() if value is not None}


class CatalogModifierGroupCreatedDetails(ModifierAuditDetails):
    """A modifier group was created (selection rule reconstructable)."""

    name: str
    item_id: str
    min_select: int
    max_select_mode: Literal["finite", "unlimited"]
    max_select: int | None = None  # present exactly when the mode is finite


class CatalogModifierGroupUpdatedDetails(ModifierAuditDetails):
    """A modifier group changed.

    ``min_select_old/new`` appear exactly when the minimum changes. The
    mode pair appears whenever the maximum changes (finite→unlimited,
    unlimited→finite, finite→different finite); the finite value fields
    appear only for the finite side(s).
    """

    changed_fields: str
    min_select_old: int | None = None
    min_select_new: int | None = None
    max_select_mode_old: Literal["finite", "unlimited"] | None = None
    max_select_mode_new: Literal["finite", "unlimited"] | None = None
    max_select_old: int | None = None
    max_select_new: int | None = None


class CatalogModifierGroupDeletedDetails(ModifierAuditDetails):
    """A modifier group was deleted (its options cascaded — no fan-out)."""

    name: str
    item_id: str
    option_count: int


class CatalogModifierOptionCreatedDetails(ModifierAuditDetails):
    """A modifier option was created."""

    name: str
    group_id: str
    price_delta_minor: int


class CatalogModifierOptionUpdatedDetails(ModifierAuditDetails):
    """A modifier option changed.

    Price old/new appear exactly when the delta changes; the availability
    pair (closed-set strings) appears exactly when availability changes.
    """

    changed_fields: str
    price_delta_minor_old: int | None = None
    price_delta_minor_new: int | None = None
    availability_old: Literal["available", "unavailable"] | None = None
    availability_new: Literal["available", "unavailable"] | None = None


class CatalogModifierOptionDeletedDetails(ModifierAuditDetails):
    """A modifier option was deleted directly (not via cascade)."""

    name: str
    group_id: str


# --- Media (M3C, ADR-017) -----------------------------------------------------
#
# Bounded values only. No storage key, filesystem path, checksum, alt text,
# or signed URL ever enters an audit payload (ruling R3/R4; final
# corrections I/L). Optional inapplicable fields are omitted at both layers
# (the M3B ModifierAuditDetails omit-None base is reused).


class MediaAssetUploadedDetails(ModifierAuditDetails):
    """A media asset was uploaded and stored (pending)."""

    source_format: Literal["jpeg", "png", "webp"]
    width: int
    height: int
    byte_size: int
    variant_count: int


class MediaAssetDeletedDetails(ModifierAuditDetails):
    """A media asset was deleted directly by an administrator."""

    status: Literal["pending", "active"]
    variant_count: int


class MediaAssetExpiredDetails(ModifierAuditDetails):
    """A pending asset was removed by the system TTL sweep (NULL actor)."""

    trigger: Literal["pending_ttl_sweep"]
    variant_count: int


class CatalogItemImageChangedDetails(ModifierAuditDetails):
    """An item's image attachment changed.

    ``change`` is the closed-set kind. The media-id pair is present per the
    exact rules (final correction 3): attached → new only; replaced → old
    and new; cleared → old only; alt_updated → old and new present and
    equal. The alt text itself is never recorded — only whether it changed.
    """

    change: Literal["attached", "replaced", "cleared", "alt_updated"]
    media_id_old: str | None = None
    media_id_new: str | None = None
    alt_text_changed: Literal["changed", "unchanged"]


# --- Storefront (M4B, ADR-020) ------------------------------------------------
#
# Bounded scalar fields only (§11, approved ruling D-8): a section
# type → count map would introduce dynamic keys and break the closed-key-
# set guarantee this file exists to give. Configuration JSON, restaurant
# copy, and tokens never enter an audit payload; draft edits are not
# audited at all.


class StorefrontPublishedDetails(AuditDetails):
    """A draft was published as a numbered version."""

    version_number: int
    design_variant: str
    schema_version: int
    section_count: int


class StorefrontVersionRestoredDetails(AuditDetails):
    """An archived version was restored into the current draft."""

    restored_from_version_number: int
    design_variant: str


class StorefrontDesignAssignedDetails(ModifierAuditDetails):
    """A platform administrator assigned the draft's design variant.

    ``previous_variant`` is present exactly when a draft already existed;
    its absence marks the first-draft creation path (ADR-020 §5.7), where
    state came into existence that did not exist before — no boolean is
    needed, keeping the projection value union string/int only. The
    omit-None base drops the inapplicable field from the stored payload
    (the M3B D6 field-presence rule).
    """

    previous_variant: str | None = None
    new_variant: str


# --- Hours (M5A, ADR-025) -----------------------------------------------------
#
# Bounded scalars only. The D6 exception note is deliberately never
# recorded — only whether one is present — so customer-facing copy stays
# out of audit payloads, and the projection value union stays string/int
# (booleans are expressed as closed-set strings, the M3B convention).


class BusinessHoursUpdatedDetails(AuditDetails):
    """The weekly schedule was replaced (one event per full-set command)."""

    interval_count: int


class ScheduleExceptionSetDetails(AuditDetails):
    """One date's override was created or replaced."""

    exception_date: str  # ISO date — a bounded string, never a free value
    kind: Literal["closed_all_day", "special_hours"]
    interval_count: int
    note: Literal["present", "absent"]


class ScheduleExceptionRemovedDetails(AuditDetails):
    """One date's override was removed (the weekly schedule resumes)."""

    exception_date: str


class FulfillmentUpdatedDetails(AuditDetails):
    """The fulfillment policy was written (full-document command).

    ``max_orders_per_slot`` (M6A, ADR-026 D3) is None for "unlimited";
    the read projection simply omits an absent cap.
    """

    pickup: Literal["enabled", "disabled"]
    asap: Literal["enabled", "disabled"]
    lead_time_minutes: int
    slot_interval_minutes: int
    last_order_before_close_minutes: int
    max_days_ahead: int
    max_orders_per_slot: int | None = None


class BusinessTimezoneChangedDetails(AuditDetails):
    """The platform corrected the tenant timezone (ruling D2).

    Both values are recorded because the change re-interprets every stored
    local time; IANA identifiers are bounded operational strings.
    """

    timezone_from: str
    timezone_to: str


class OrderPlacedDetails(AuditDetails):
    """A guest placed an order (M6A, ADR-026 — a NULL-actor event).

    Ids, counts, and totals only: never the customer's name, contact,
    consents, instructions, or the tracking token (blueprint §7.8).
    """

    order_number: int
    line_count: int
    total_minor: int
    pickup_kind: Literal["asap", "scheduled"]


class OrderCancelledByCustomerDetails(AuditDetails):
    """The customer cancelled their submitted order (M6B, ruling D11)."""

    order_number: int
