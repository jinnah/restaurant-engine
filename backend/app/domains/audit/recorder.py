"""Audit event recorder (M2A).

The single write path to ``audit_events``. It participates in the
*caller's* transaction and never commits: an audit event and the change it
records are durable together or not at all (approved proposal §13). The
table is append-only — this module deliberately exposes no update or
delete operation.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.correlation import get_request_id
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import AuditDetails
from app.domains.audit.models import AuditEvent


def record(
    session: Session,
    action: AuditAction,
    *,
    actor_user_id: uuid.UUID | None,
    business_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: AuditDetails | None = None,
) -> None:
    """Append one audit event inside the caller's open transaction.

    ``details`` accepts only the typed per-action schemas — the closed,
    secret-free key set is the contract (see audit.details).
    """
    session.add(
        AuditEvent(
            occurred_at=datetime.now(UTC),
            action=action.value,
            actor_user_id=actor_user_id,
            business_id=business_id,
            target_type=target_type,
            target_id=target_id,
            correlation_id=get_request_id(),
            details=details.model_dump(mode="json") if details is not None else None,
        )
    )
