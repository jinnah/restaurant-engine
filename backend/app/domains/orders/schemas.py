"""Orders API schemas (M6A, ADR-026).

Command input is strict (extra fields rejected — blueprint §11.3) and
every text field runs the domain normalize/control-character policy at
the boundary, so the service and the pure core only ever see canonical
text. Public response schemas are separate types (the M3D convention);
the tracking projection deliberately carries **no customer fields**
(review amendment: a tracking URL is shareable by design).
"""

import uuid
from datetime import datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.businesses.schemas import PublicSiteSummary
from app.domains.orders import policies
from app.domains.orders.lifecycle import OrderStatus, PickupKind


def _required_line(value: str, *, max_length: int, label: str) -> str:
    if policies.has_control_characters(value):
        msg = f"{label} must not contain control characters"
        raise ValueError(msg)
    text = policies.normalize_line(value)
    if not text:
        msg = f"{label} must not be blank"
        raise ValueError(msg)
    if len(text) > max_length:
        msg = f"{label} must be at most {max_length} characters"
        raise ValueError(msg)
    return text


def _optional_block(value: str | None, *, max_length: int, label: str) -> str | None:
    if value is None:
        return None
    if policies.has_control_characters(value, allow_newline=True):
        msg = f"{label} must not contain control characters"
        raise ValueError(msg)
    text = policies.normalize_block(value)
    if not text:
        return None
    if len(text) > max_length:
        msg = f"{label} must be at most {max_length} characters"
        raise ValueError(msg)
    return text


class CartLineIn(BaseModel):
    """One submitted cart line: references plus quantity, never prices."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    quantity: int = Field(ge=policies.MIN_LINE_QUANTITY, le=policies.MAX_LINE_QUANTITY)
    option_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    item_instructions: str | None = None

    @field_validator("item_instructions")
    @classmethod
    def _instructions(cls, value: str | None) -> str | None:
        return _optional_block(
            value,
            max_length=policies.MAX_ITEM_INSTRUCTIONS_LENGTH,
            label="item_instructions",
        )


class OrderPlace(BaseModel):
    """The idempotent placement command (blueprint §7.7; rulings D2/D7/D8).

    ``expected_total_minor`` is the client's displayed total — compared,
    never used in arithmetic. The two consents are independent required
    booleans (never a blended opt-in). ``requested_pickup_at`` is
    required exactly when ``pickup_kind`` is ``scheduled``.
    """

    model_config = ConfigDict(extra="forbid")

    idempotency_key: uuid.UUID
    lines: list[CartLineIn] = Field(min_length=1, max_length=policies.MAX_LINES_PER_ORDER)
    customer_name: str
    customer_phone: str
    customer_email: str | None = None
    order_instructions: str | None = None
    consent_updates: bool
    consent_marketing: bool
    pickup_kind: PickupKind
    requested_pickup_at: AwareDatetime | None = None
    expected_total_minor: int = Field(ge=0, le=policies.MAX_TOTAL_MINOR)

    @field_validator("customer_name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required_line(
            value, max_length=policies.MAX_CUSTOMER_NAME_LENGTH, label="customer_name"
        )

    @field_validator("customer_phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return _required_line(
            value, max_length=policies.MAX_CUSTOMER_PHONE_LENGTH, label="customer_phone"
        )

    @field_validator("customer_email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if policies.has_control_characters(value):
            msg = "customer_email must not contain control characters"
            raise ValueError(msg)
        text = policies.normalize_line(value)
        if not text:
            return None
        if len(text) > policies.MAX_CUSTOMER_EMAIL_LENGTH:
            msg = "customer_email must be at most 254 characters"
            raise ValueError(msg)
        return text

    @field_validator("order_instructions")
    @classmethod
    def _instructions(cls, value: str | None) -> str | None:
        return _optional_block(
            value,
            max_length=policies.MAX_ORDER_INSTRUCTIONS_LENGTH,
            label="order_instructions",
        )

    @model_validator(mode="after")
    def _pickup_shape(self) -> Self:
        if self.pickup_kind is PickupKind.SCHEDULED and self.requested_pickup_at is None:
            msg = "requested_pickup_at is required for a scheduled pickup"
            raise ValueError(msg)
        if self.pickup_kind is PickupKind.ASAP and self.requested_pickup_at is not None:
            msg = "requested_pickup_at must be omitted for an ASAP pickup"
            raise ValueError(msg)
        return self


class PublicOrderLineOption(BaseModel):
    """One snapshotted option, as stored — never re-read from catalog."""

    group_name: str
    option_name: str
    price_delta_minor: int


class PublicOrderLine(BaseModel):
    display_name: str
    quantity: int
    base_price_minor: int
    options: list[PublicOrderLineOption]
    line_total_minor: int


class PublicOrderView(BaseModel):
    """The customer-facing order projection (tracking and placement).

    Carries the snapshot and the promise — and no customer PII (review
    amendment): a tracking URL is shareable by design, so the name,
    contact, consents, and instructions the order stores never appear
    here.
    """

    business: PublicSiteSummary
    order_number: int
    status: OrderStatus
    placed_at: datetime
    business_timezone: str
    pickup_kind: PickupKind
    promised_pickup_at: datetime
    currency: str
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    lines: list[PublicOrderLine]


class OrderPlacedResponse(BaseModel):
    """The placement answer: the order plus its tracking token.

    The token appears here and nowhere else, ever (ruling D4): it is not
    stored in clear, not logged, not audited, and not returned by the
    tracking route it authorizes.
    """

    tracking_token: str
    order: PublicOrderView
