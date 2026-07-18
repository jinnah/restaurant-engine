"""Audit read models (M2D, ADR-014).

Pure, parameterized queries — no authorization here. The application/API
composition layer owns capability enforcement and the safe projection
(``app/api/audit_view.py``); keeping authz out of the audit domain keeps
the dependency graph acyclic (identity → audit must never reverse).

Cursor pagination on the BIGINT identity id (designed for this in M2A):
``ORDER BY id DESC`` with an exclusive ``id < before_id`` cursor. Rows are
immutable and ids monotonic, so pages are stable while new events arrive —
new rows can only appear before the first page, never shift later ones.
"""

import uuid
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditEvent


def _apply_common_filters(
    statement: Select[tuple[AuditEvent]],
    *,
    before_id: int | None,
    action: str | None,
    occurred_after: datetime | None,
    occurred_before: datetime | None,
) -> Select[tuple[AuditEvent]]:
    if before_id is not None:
        statement = statement.where(AuditEvent.id < before_id)  # exclusive cursor
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    if occurred_after is not None:
        statement = statement.where(AuditEvent.occurred_at > occurred_after)
    if occurred_before is not None:
        statement = statement.where(AuditEvent.occurred_at < occurred_before)
    return statement


def platform_page(
    db: Session,
    *,
    limit: int,
    before_id: int | None = None,
    action: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
    business_id: uuid.UUID | None = None,
) -> list[AuditEvent]:
    """One platform-wide page (platform-capability-gated by the caller)."""
    statement = _apply_common_filters(
        select(AuditEvent),
        before_id=before_id,
        action=action,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if business_id is not None:
        statement = statement.where(AuditEvent.business_id == business_id)
    return list(db.execute(statement.order_by(AuditEvent.id.desc()).limit(limit)).scalars())


def business_page(
    db: Session,
    *,
    business_id: uuid.UUID,
    limit: int,
    before_id: int | None = None,
    action: str | None = None,
    occurred_after: datetime | None = None,
    occurred_before: datetime | None = None,
) -> list[AuditEvent]:
    """One business-scoped page.

    Both tenant predicates are explicit and unconditional (ADR-014
    correction H): rows must belong to exactly this business, and
    platform-level rows (``business_id IS NULL`` — logins, admin actions)
    are structurally excluded even if the equality predicate were ever
    rewritten.
    """
    statement = _apply_common_filters(
        select(AuditEvent).where(
            AuditEvent.business_id == business_id,
            AuditEvent.business_id.is_not(None),
        ),
        before_id=before_id,
        action=action,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
    )
    return list(db.execute(statement.order_by(AuditEvent.id.desc()).limit(limit)).scalars())
