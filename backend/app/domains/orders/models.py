"""Orders persistence models (M6A, ADR-026).

The blueprint §9 order tables plus the transactional outbox. Every order
table is tenant-owned — ``business_id`` leads every index and unique —
and the child tables use composite tenant-safe foreign keys (docs/04), so
a line can never reference another tenant's order.

**Snapshots reference nothing** (ruling D1): lines and options store
display names, prices, and bare provenance UUIDs with **no** foreign key
to catalog. Deleting a menu item referenced by an order snapshot is safe
because the snapshot never looks at catalog again (blueprint §7.3).

``orders.placed_at`` is a UTC instant and ``orders.business_timezone`` is
the tenant zone at placement — the ADR-025 obligation: an order's display
time is a stored pair, never re-derived from the live Business (whose
timezone the platform may later correct).

``tax_minor``, ``discount_total_minor``, and ``applied_promotions`` are
present-but-frozen (rulings D6/D7): the CHECKs pin them to zero/empty so
every historical snapshot already carries the columns later milestones
populate, and no past order can change retroactively when they do.

``outbox_messages`` is deliberately **platform-global** (documented per
docs/04): a future worker claims work across tenants; ``business_id`` is
carried for attribution and cleanup, not scoping.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Order(Base):
    """One placed order — immutable except ``status`` (guarded commands)."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    # Tenant-scoped, dense from 1, non-secret (blueprint §9.1) — the number
    # staff and customers say out loud. Allocated under the Business lock.
    order_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # 256-bit token, stored only as its SHA-256 hex digest (ruling D4).
    tracking_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_timezone: Mapped[str] = mapped_column(Text, nullable=False)

    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str] = mapped_column(Text, nullable=False)
    customer_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Two separate, independently recorded choices (ruling D7) — never a
    # single blended opt-in (docs/08 strengthened commitments).
    consent_updates: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, nullable=False)

    pickup_kind: Mapped[str] = mapped_column(Text, nullable=False)
    promised_pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # M7A (ADR-027 ruling D7): the kitchen's live prep estimate. The
    # promise above stays immutable as placed; this is the updatable
    # answer, shown on the tracker when present.
    estimated_ready_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    applied_promotions: Mapped[list] = mapped_column(  # type: ignore[type-arg]
        JSONB, nullable=False, default=list
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # The composite target every tenant-safe child FK points at.
        UniqueConstraint("business_id", "id"),
        UniqueConstraint("business_id", "order_number"),
        # Token digests are compared globally on the tracking route after
        # host resolution; uniqueness makes the digest an identity.
        UniqueConstraint("tracking_token_digest"),
        CheckConstraint(
            "status IN ('submitted', 'accepted', 'preparing', 'ready',"
            " 'completed', 'rejected', 'cancelled')",
            name="status_known",
        ),
        CheckConstraint("pickup_kind IN ('asap', 'scheduled')", name="pickup_kind_known"),
        CheckConstraint("order_number >= 1", name="order_number_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso4217_shape"),
        CheckConstraint("subtotal_minor >= 0", name="subtotal_nonnegative"),
        CheckConstraint("total_minor >= 0", name="total_nonnegative"),
        # Rulings D6/D7: present-but-frozen until their milestones.
        CheckConstraint("tax_minor = 0", name="tax_frozen_m6"),
        CheckConstraint("discount_total_minor = 0", name="discount_frozen_m6"),
        CheckConstraint("applied_promotions = '[]'::jsonb", name="promotions_frozen_m6"),
        # §9.2: stored totals agree at creation, permanently.
        CheckConstraint(
            "total_minor = subtotal_minor + tax_minor - discount_total_minor",
            name="total_components_agree",
        ),
        Index("ix_orders_business_placed", "business_id", "placed_at"),
        # The D3 throttle count: non-cancelled orders per promised slot.
        Index("ix_orders_business_promised", "business_id", "promised_pickup_at"),
    )


class OrderLine(Base):
    """One immutable item snapshot (ruling D1: no catalog FK)."""

    __tablename__ = "order_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_provenance_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    base_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    item_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("business_id", "id"),
        ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("business_id", "order_id", "position"),
        CheckConstraint("quantity BETWEEN 1 AND 50", name="quantity_bounds"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("base_price_minor >= 0", name="base_price_nonnegative"),
        CheckConstraint("line_total_minor >= 0", name="line_total_nonnegative"),
    )


class OrderLineOption(Base):
    """One immutable modifier-option snapshot on a line (ruling D1)."""

    __tablename__ = "order_line_options"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    line_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    group_provenance_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    option_provenance_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    group_display_name: Mapped[str] = mapped_column(Text, nullable=False)
    option_display_name: Mapped[str] = mapped_column(Text, nullable=False)
    price_delta_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "line_id"],
            ["order_lines.business_id", "order_lines.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("business_id", "line_id", "position"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("price_delta_minor >= 0", name="price_delta_nonnegative"),
    )


class OrderStatusEvent(Base):
    """Append-only transition history (blueprint §7.7).

    The placement event has ``from_status IS NULL``; every later row
    records a real transition. Rows are never updated or deleted — the
    §9.2 "status event history cannot be silently rewritten" invariant is
    structural (no update path exists in the domain).
    """

    __tablename__ = "order_status_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("actor_kind IN ('customer', 'member', 'system')", name="actor_kind_known"),
        Index("ix_order_status_events_order", "business_id", "order_id", "occurred_at"),
    )


class IdempotencyKey(Base):
    """One accepted idempotent command (ruling D2; blueprint §9.2).

    The unique triple makes a retried placement a read: the stored
    ``order_id`` is the answer. ``request_digest`` (SHA-256 of the
    canonical payload) distinguishes an honest retry from key reuse with
    a different cart, which is a typed 409 — never a second order.
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("business_id", "operation", "idempotency_key"),
        ForeignKeyConstraint(
            ["business_id", "order_id"],
            ["orders.business_id", "orders.id"],
            ondelete="CASCADE",
        ),
    )


class OutboxMessage(Base):
    """One durable side-effect intent (blueprint §14.2; ruling D14).

    Written in the same transaction as the change it announces. **No
    worker exists in M6** — rows accumulate as ``pending`` until the
    first channel milestone ships the poller with its first real
    handler. ``payload`` carries ids and facts only, never PII.

    Platform-global (documented, docs/04): a worker claims across
    tenants; ``business_id`` is attribution, not scoping.
    """

    __tablename__ = "outbox_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("businesses.id", ondelete="RESTRICT"), nullable=True
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    # The §9.2 harmful-duplication tie: at most one message per topic per
    # order. Nullable so non-order topics can exist later; PostgreSQL
    # treats NULLs as distinct, exactly the semantics wanted.
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # type: ignore[type-arg]
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("topic", "order_id"),
        CheckConstraint("status IN ('pending', 'processed', 'dead')", name="status_known"),
        CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
        Index("ix_outbox_pending", "status", "created_at"),
    )
