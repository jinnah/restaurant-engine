"""Business membership invitations (M2D, ADR-014).

Onboarding state owned by businesses (blueprint §7.2). Identity remains
the sole owner of user/membership **writes**: acceptance calls identity's
narrow no-commit creation functions inside one transaction here — never
identity's ORM models.

Concurrency (ADR-014 correction B): every workflow follows the global
lock order **Business → Invitation → User**, so issuance, replacement,
revocation, acceptance, and the M2B lifecycle transitions serialize
instead of deadlocking. Partial unique indexes are backstops, not the
primary mechanism; any race that reaches one is converted to this
surface's uniform response.

Authorization (correction C): the role ceiling governs issue, replace,
and revoke alike — the actor must be authorized for
``max(existing invitation's role, proposed role)``. A manager can neither
mint an owner nor interfere with a pending owner invitation. Platform
administrators manage any role through the platform route only.

New-user acceptance is two-phase (correction A): cheap lock-free
prevalidation → Argon2 outside any transaction → locked revalidation and
atomic apply. Every public failure mode raises the identical neutral 404.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import (
    ConflictError,
    InvalidStateError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from app.core.settings import Settings
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import InvitationDetails
from app.domains.businesses.lifecycle import BusinessStatus
from app.domains.businesses.models import Business, BusinessInvitation
from app.domains.identity import memberships
from app.domains.identity.actor import ActorContext
from app.domains.identity.authorization import require_membership_capability
from app.domains.identity.policies import (
    Capability,
    Role,
    require_platform_capability,
    role_outranks,
)
from app.domains.identity.service import (
    create_user_from_invitation,
    find_user_id_by_email,
    normalize_email,
)

_INVALID_INVITATION_MESSAGE = "Invitation is not valid or has expired."

# Statuses in which a business may take on new members.
_JOINABLE = (BusinessStatus.PROVISIONING.value, BusinessStatus.ACTIVE.value)


@dataclass(frozen=True)
class IssuedInvitation:
    """One-time issuance result; the raw token is never seen again."""

    token: str
    invitation_id: uuid.UUID
    expires_at: datetime
    email_normalized: str
    role: Role


@dataclass(frozen=True)
class InvitationPreviewResult:
    business_name: str
    role: Role
    email_hint: str


@dataclass(frozen=True)
class AcceptedInvitation:
    business_id: uuid.UUID
    email_normalized: str
    role: Role


def mask_email(email_normalized: str) -> str:
    """Deterministic PII-minimizing hint (ADR-014 correction E).

    First character of the local part (or ``*`` when it has fewer than two
    characters) + ``***`` + the full domain. The complete local part is
    never derivable from the hint.
    """
    local, _, domain = email_normalized.partition("@")
    first = local[0] if len(local) >= 2 else "*"
    return f"{first}***@{domain}"


def _authorize_issue(
    db: Session, actor: ActorContext, business_id: uuid.UUID, *, via_platform: bool
) -> Role | None:
    """Capability gate for invitation management; returns the actor's
    business role (None on the platform route, which has no rank ceiling)."""
    if via_platform:
        require_platform_capability(actor, Capability.PLATFORM_BUSINESSES_MANAGE)
        return None
    return require_membership_capability(
        db, actor, business_id=business_id, capability=Capability.BUSINESS_MEMBERS_INVITE
    )


def _require_rank(actor_role: Role | None, target_role: Role) -> None:
    """Correction C: the ceiling applies to every managed invitation role."""
    if actor_role is not None and role_outranks(target_role, actor_role):
        raise PermissionDeniedError("You cannot manage an invitation for a role above your own.")


def _lock_business(db: Session, business_id: uuid.UUID) -> Business | None:
    return db.execute(
        select(Business).where(Business.id == business_id).with_for_update()
    ).scalar_one_or_none()


def issue_invitation(
    db: Session,
    settings: Settings,
    actor: ActorContext,
    business_id: uuid.UUID,
    *,
    email: str,
    role: Role,
    via_platform: bool,
) -> IssuedInvitation:
    """Issue (or replace) the live invitation for a business + email.

    Reissue semantics: an existing pending invitation for the same email is
    revoked and replaced in the same transaction — the actor must be
    authorized for both the existing role and the new one. Issuance never
    discloses whether an account exists for the email.
    """
    actor_role = _authorize_issue(db, actor, business_id, via_platform=via_platform)
    _require_rank(actor_role, role)
    email_normalized = normalize_email(email)

    # Lock order: Business first.
    business = _lock_business(db, business_id)
    if business is None:
        # Platform route only: membership authz already 404s for nonmembers.
        raise ResourceNotFoundError("Business not found.")
    if business.status not in _JOINABLE:
        raise InvalidStateError(f"cannot invite members to a {business.status} business")

    # Already a member? (Visible only to authorized inviters of this
    # business — platform-wide account existence is not disclosed.)
    existing_user_id = find_user_id_by_email(db, email_normalized=email_normalized)
    if existing_user_id is not None:
        existing_role = memberships.get_role(db, business_id=business_id, user_id=existing_user_id)
        if existing_role is not None:
            raise ConflictError("That email already belongs to a member of this business.")

    # Replace any live predecessor (Invitation lock second).
    predecessor = db.execute(
        select(BusinessInvitation)
        .where(
            BusinessInvitation.business_id == business_id,
            BusinessInvitation.email_normalized == email_normalized,
            BusinessInvitation.accepted_at.is_(None),
            BusinessInvitation.revoked_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if predecessor is not None:
        _require_rank(actor_role, Role(predecessor.role))
        predecessor.revoked_at = func.now()
        recorder.record(
            db,
            AuditAction.BUSINESS_INVITATION_REVOKED,
            actor_user_id=actor.user.id,
            business_id=business_id,
            target_type="invitation",
            target_id=str(predecessor.id),
            details=InvitationDetails(email_normalized=email_normalized, role=predecessor.role),
        )
        # The partial unique index treats the predecessor as live until this
        # transaction's UPDATE is visible; flush it before the insert.
        db.flush()

    raw_token = security.generate_opaque_token()
    invitation = BusinessInvitation(
        business_id=business_id,
        email=email.strip(),
        email_normalized=email_normalized,
        role=role.value,
        token_hash=security.hash_opaque_token(raw_token),
        invited_by_user_id=actor.user.id,
        # Database clock (ADR-014).
        expires_at=func.now() + func.make_interval(0, 0, 0, settings.invitation_expiry_days),
    )
    db.add(invitation)
    try:
        db.flush()
    except IntegrityError:
        # Backstop: a concurrent issuer slipped past the locks.
        db.rollback()
        raise ConflictError("An invitation for that email already exists.") from None
    db.refresh(invitation)
    recorder.record(
        db,
        AuditAction.BUSINESS_INVITATION_ISSUED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="invitation",
        target_id=str(invitation.id),
        details=InvitationDetails(email_normalized=email_normalized, role=role.value),
    )
    db.commit()
    return IssuedInvitation(
        token=raw_token,
        invitation_id=invitation.id,
        expires_at=invitation.expires_at,
        email_normalized=email_normalized,
        role=role,
    )


def revoke_invitation(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    invitation_id: uuid.UUID,
    *,
    via_platform: bool,
) -> None:
    """Revoke a pending invitation.

    Deliberately allowed for suspended and closed businesses (outstanding
    credentials must always be invalidatable). Tenant-scoped: an invitation
    id outside this business is an indistinguishable 404.
    """
    actor_role = _authorize_issue(db, actor, business_id, via_platform=via_platform)

    business = _lock_business(db, business_id)
    if business is None:
        raise ResourceNotFoundError("Business not found.")
    invitation = db.execute(
        select(BusinessInvitation)
        .where(
            BusinessInvitation.id == invitation_id,
            BusinessInvitation.business_id == business_id,
            BusinessInvitation.accepted_at.is_(None),
            BusinessInvitation.revoked_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if invitation is None:
        raise ResourceNotFoundError("Invitation not found.")
    _require_rank(actor_role, Role(invitation.role))
    invitation.revoked_at = func.now()
    recorder.record(
        db,
        AuditAction.BUSINESS_INVITATION_REVOKED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="invitation",
        target_id=str(invitation.id),
        details=InvitationDetails(
            email_normalized=invitation.email_normalized, role=invitation.role
        ),
    )
    db.commit()


@dataclass(frozen=True)
class PendingInvitation:
    """Projection row for the operational pending list (no token, ever)."""

    invitation_id: uuid.UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime
    state: str  # "pending" | "expired" — decided on the database clock
    invited_by_user_id: uuid.UUID


def list_pending_invitations(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    via_platform: bool,
) -> tuple[list[PendingInvitation], int]:
    """Pending-only operational list; history lives in the audit trail."""
    _authorize_issue(db, actor, business_id, via_platform=via_platform)
    if via_platform and db.get(Business, business_id) is None:
        raise ResourceNotFoundError("Business not found.")

    live = (
        BusinessInvitation.accepted_at.is_(None),
        BusinessInvitation.revoked_at.is_(None),
        BusinessInvitation.business_id == business_id,
    )
    total = db.execute(
        select(func.count()).select_from(BusinessInvitation).where(*live)
    ).scalar_one()
    rows = db.execute(
        select(BusinessInvitation, BusinessInvitation.expires_at > func.now())
        .where(*live)
        .order_by(BusinessInvitation.created_at.desc(), BusinessInvitation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        PendingInvitation(
            invitation_id=invitation.id,
            email=invitation.email_normalized,
            role=Role(invitation.role),
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            state="pending" if is_live else "expired",
            invited_by_user_id=invitation.invited_by_user_id,
        )
        for invitation, is_live in rows
    ]
    return items, int(total)


def _usable_invitation(
    db: Session, token_hash: str, *, for_update: bool
) -> tuple[BusinessInvitation, Business] | None:
    """The invitation + business iff redeemable right now (SQL-clock)."""
    statement = (
        select(BusinessInvitation, Business)
        .join(Business, Business.id == BusinessInvitation.business_id)
        .where(
            BusinessInvitation.token_hash == token_hash,
            BusinessInvitation.accepted_at.is_(None),
            BusinessInvitation.revoked_at.is_(None),
            BusinessInvitation.expires_at > func.now(),
            Business.status.in_(_JOINABLE),
        )
    )
    if for_update:
        statement = statement.with_for_update(of=BusinessInvitation)
    row = db.execute(statement).first()
    return (row[0], row[1]) if row is not None else None


def preview_invitation(db: Session, *, token: str) -> InvitationPreviewResult:
    """Public preview for the accept page: business name, role, masked email."""
    found = _usable_invitation(db, security.hash_opaque_token(token), for_update=False)
    if found is None:
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    invitation, business = found
    return InvitationPreviewResult(
        business_name=business.name,
        role=Role(invitation.role),
        email_hint=mask_email(invitation.email_normalized),
    )


def accept_invitation_new_user(
    db: Session, *, token: str, display_name: str, password: str
) -> AcceptedInvitation:
    """Public acceptance creating the account + membership (two-phase).

    No auto-login: the caller signs in through the normal login flow.
    A token whose email became a registered account is indistinguishable
    from an invalid token (uniform 404).
    """
    token_hash = security.hash_opaque_token(token)

    # Phase 1 — cheap prevalidation; no Argon2 for invalid tokens.
    found = _usable_invitation(db, token_hash, for_update=False)
    if found is None:
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    invitation, _business = found
    business_id = invitation.business_id
    email_normalized = invitation.email_normalized
    if find_user_id_by_email(db, email_normalized=email_normalized) is not None:
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    db.rollback()

    password_hash = security.hash_password(password)

    # Phase 2 — authoritative: Business → Invitation → user insert.
    business = _lock_business(db, business_id)
    locked = _usable_invitation(db, token_hash, for_update=True)
    if business is None or locked is None:
        db.rollback()
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    invitation = locked[0]
    try:
        user_id = create_user_from_invitation(
            db,
            email=invitation.email,
            email_normalized=email_normalized,
            display_name=display_name,
            password_hash=password_hash,
        )
        memberships.create(db, business_id=business_id, user_id=user_id, role=Role(invitation.role))
    except IntegrityError:
        # Email registered (or membership raced) since prevalidation: the
        # locked flow still fails closed to the uniform response.
        db.rollback()
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE) from None
    invitation.accepted_at = func.now()
    invitation.accepted_user_id = user_id
    recorder.record(
        db,
        AuditAction.BUSINESS_INVITATION_ACCEPTED,
        actor_user_id=user_id,
        business_id=business_id,
        target_type="invitation",
        target_id=str(invitation.id),
        details=InvitationDetails(email_normalized=email_normalized, role=invitation.role),
    )
    db.commit()
    return AcceptedInvitation(
        business_id=business_id,
        email_normalized=email_normalized,
        role=Role(invitation.role),
    )


def accept_invitation_existing_user(
    db: Session, actor: ActorContext, *, token: str
) -> AcceptedInvitation:
    """Authenticated acceptance adding a membership to the actor's account.

    The supported path for one user to belong to multiple businesses
    (ruling 3). The actor's normalized email must match the invitation's —
    someone else's token is an indistinguishable 404. No Argon2 involved.
    """
    token_hash = security.hash_opaque_token(token)

    found = _usable_invitation(db, token_hash, for_update=False)
    if found is None:
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    business_id = found[0].business_id

    business = _lock_business(db, business_id)
    locked = _usable_invitation(db, token_hash, for_update=True)
    if business is None or locked is None:
        db.rollback()
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    invitation = locked[0]
    if normalize_email(actor.user.email) != invitation.email_normalized:
        db.rollback()
        raise ResourceNotFoundError(_INVALID_INVITATION_MESSAGE)
    try:
        memberships.create(
            db, business_id=business_id, user_id=actor.user.id, role=Role(invitation.role)
        )
    except IntegrityError:
        # Their own membership already exists — honest, non-leaking conflict.
        db.rollback()
        raise ConflictError("You are already a member of this business.") from None
    invitation.accepted_at = func.now()
    invitation.accepted_user_id = actor.user.id
    recorder.record(
        db,
        AuditAction.BUSINESS_INVITATION_ACCEPTED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="invitation",
        target_id=str(invitation.id),
        details=InvitationDetails(
            email_normalized=invitation.email_normalized, role=invitation.role
        ),
    )
    db.commit()
    return AcceptedInvitation(
        business_id=business_id,
        email_normalized=invitation.email_normalized,
        role=Role(invitation.role),
    )
