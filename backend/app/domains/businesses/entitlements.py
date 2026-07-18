"""Feature-entitlement service (M2D, ADR-014).

Platform-controlled (governance split, blueprint §12.3): only
``platform.businesses.manage`` mutates a business's feature set; members
read their effective set through ``business.view``. Presence means
enabled; everything defaults to disabled.

Fail-closed unknown-key policy (correction I): a stored key that is not
in the code registry — manual SQL, drift, or a future rollback — is never
surfaced as enabled. Reads exclude it and emit a structured error-level
log; the next full-set replacement deletes it (audited), so unknown rows
are cleaned up rather than silently legitimized.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import InvalidStateError, ResourceNotFoundError
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import EntitlementDetails
from app.domains.businesses.features import FeatureKey, is_known_feature
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.models import Business, FeatureEntitlement
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import Capability, require_platform_capability

_logger = structlog.get_logger("app.entitlements")


def _report_unknown_keys(business_id: uuid.UUID, unknown: list[str]) -> None:
    for key in unknown:
        # Operational invariant alarm: rows like this can only come from
        # manual SQL or registry drift. Never enabled, never returned.
        _logger.error(
            "entitlement_unknown_key",
            business_id=str(business_id),
            feature_key=key[:100],
        )


def set_entitlements(
    db: Session, actor: ActorContext, business_id: uuid.UUID, *, features: set[FeatureKey]
) -> list[FeatureKey]:
    """Full-set replacement of a business's entitlements (platform only).

    Serialized on the business row lock; the diff is audited per key.
    Closed businesses are immutable (409); provisioning, active, and
    suspended may be configured. Unknown *stored* rows are deleted by any
    replacement (never legitimized); unknown *requested* keys are already
    rejected by schema validation (422).
    """
    require_platform_capability(actor, Capability.PLATFORM_BUSINESSES_MANAGE)

    business = db.execute(
        select(Business).where(Business.id == business_id).with_for_update()
    ).scalar_one_or_none()
    if business is None:
        raise ResourceNotFoundError("Business not found.")
    if business.status == BusinessStatus.CLOSED.value:
        raise InvalidStateError("cannot change entitlements of a closed business")

    stored_rows = (
        db.execute(select(FeatureEntitlement).where(FeatureEntitlement.business_id == business_id))
        .scalars()
        .all()
    )
    desired_values = {feature.value for feature in features}
    stored_values = {row.feature_key for row in stored_rows}
    _report_unknown_keys(
        business_id, sorted(value for value in stored_values if not is_known_feature(value))
    )

    for row in stored_rows:
        if row.feature_key not in desired_values:
            db.delete(row)
            recorder.record(
                db,
                AuditAction.BUSINESS_ENTITLEMENT_REVOKED,
                actor_user_id=actor.user.id,
                business_id=business_id,
                target_type="feature",
                target_id=row.feature_key,
                details=EntitlementDetails(feature_key=row.feature_key),
            )
    for value in sorted(desired_values - stored_values):
        db.add(FeatureEntitlement(business_id=business_id, feature_key=value))
        recorder.record(
            db,
            AuditAction.BUSINESS_ENTITLEMENT_GRANTED,
            actor_user_id=actor.user.id,
            business_id=business_id,
            target_type="feature",
            target_id=value,
            details=EntitlementDetails(feature_key=value),
        )
    db.commit()
    return sorted(features)


def get_effective_features(
    db: Session, actor: ActorContext, business_id: uuid.UUID
) -> list[FeatureKey]:
    """The business's enabled features, visible to any member.

    Fail-closed: only registry keys are ever returned.
    """
    require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_VIEW
    )
    stored = (
        db.execute(
            select(FeatureEntitlement.feature_key).where(
                FeatureEntitlement.business_id == business_id
            )
        )
        .scalars()
        .all()
    )
    _report_unknown_keys(business_id, sorted(v for v in stored if not is_known_feature(v)))
    return sorted(FeatureKey(value) for value in stored if is_known_feature(value))
