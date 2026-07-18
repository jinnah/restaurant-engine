"""Password recovery: admin-issued single-use reset tokens (M2D, ADR-014).

Self-service reset is deferred to the first email channel (M6+); the M2D
interim is a **platform-administrator-issued** token handed to the user out
of band. ``platform.users.recover`` is account-takeover-equivalent
authority: every issuance is audited, there is no public issuance path,
and the raw token appears exactly once — in the issuance response body.

Redemption is two-phase (ADR-014 correction A): a cheap read-only
prevalidation rejects invalid tokens **before** any Argon2 work, so an
unauthenticated attacker cannot force expensive hashing; the locked
re-read inside the write transaction is the authoritative check. Lock
order is User → ResetToken, shared with issuance, so the two workflows
serialize instead of deadlocking. All lifecycle timestamps are decided on
the database clock.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import security
from app.core.errors import InvalidStateError, ResourceNotFoundError
from app.core.settings import Settings
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import PasswordResetDetails
from app.domains.identity.actor import ActorContext
from app.domains.identity.models import PasswordResetToken, User
from app.domains.identity.policies import Capability, require_platform_capability
from app.domains.identity.service import normalize_email, revoke_all_sessions

_INVALID_TOKEN_MESSAGE = "Reset token is not valid or has expired."  # noqa: S105


@dataclass(frozen=True)
class IssuedReset:
    """The one-time issuance result; the raw token is never seen again."""

    token: str
    expires_at: datetime
    email_normalized: str


def issue_reset(db: Session, settings: Settings, actor: ActorContext, *, email: str) -> IssuedReset:
    """Issue a single-use reset token for an account (platform only).

    Revokes any live predecessor under the user row lock (one-live-token
    invariant; the partial unique index is the backstop). Unknown email →
    404; inactive account → 409 (the kill-switch stays authoritative).
    """
    require_platform_capability(actor, Capability.PLATFORM_USERS_RECOVER)
    email_normalized = normalize_email(email)

    # Lock the user row first (global lock order: User → ResetToken).
    user = db.execute(
        select(User).where(User.email_normalized == email_normalized).with_for_update()
    ).scalar_one_or_none()
    if user is None:
        raise ResourceNotFoundError("No account exists for that email.")
    if not user.is_active:
        raise InvalidStateError("cannot issue a reset for an inactive account")

    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    raw_token = security.generate_opaque_token()
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=security.hash_opaque_token(raw_token),
        issued_by_user_id=actor.user.id,
        # Database clock (ADR-014): the application clock never participates
        # in expiry decisions.
        expires_at=func.now()
        + func.make_interval(0, 0, 0, 0, 0, settings.password_reset_expiry_minutes),
    )
    db.add(reset)
    db.flush()
    db.refresh(reset)
    recorder.record(
        db,
        AuditAction.AUTH_PASSWORD_RESET_ISSUED,
        actor_user_id=actor.user.id,
        target_type="user",
        target_id=str(user.id),
        details=PasswordResetDetails(email_normalized=email_normalized),
    )
    db.commit()
    return IssuedReset(
        token=raw_token, expires_at=reset.expires_at, email_normalized=email_normalized
    )


def _usable_reset_row(
    db: Session, token_hash: str, *, for_update: bool
) -> PasswordResetToken | None:
    """The reset row iff it is fully usable right now (SQL-clock checks)."""
    statement = (
        select(PasswordResetToken)
        .join(User, User.id == PasswordResetToken.user_id)
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.revoked_at.is_(None),
            PasswordResetToken.expires_at > func.now(),
            User.is_active.is_(True),
        )
    )
    if for_update:
        # Lock only the token row here; the user row is locked separately
        # first to preserve the User → ResetToken order.
        statement = statement.with_for_update(of=PasswordResetToken)
    return db.execute(statement).scalar_one_or_none()


def redeem_reset(db: Session, *, token: str, new_password: str) -> None:
    """Redeem a reset token and set a new password (public, two-phase).

    Every failure mode raises the identical neutral 404 so token state is
    not disclosed. On success: password updated, login-backoff state
    cleared, **every session revoked**, token consumed — one transaction.
    """
    token_hash = security.hash_opaque_token(token)

    # Phase 1 — cheap, lock-free prevalidation. Grants no authority; exists
    # solely so invalid tokens never reach Argon2 (correction A).
    preliminary = _usable_reset_row(db, token_hash, for_update=False)
    if preliminary is None:
        raise ResourceNotFoundError(_INVALID_TOKEN_MESSAGE)
    user_id = preliminary.user_id
    # Close the read transaction before the expensive KDF (M2A discipline).
    db.rollback()

    password_hash = security.hash_password(new_password)

    # Phase 2 — authoritative locked revalidation and atomic apply.
    user = db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update()
    ).scalar_one_or_none()
    reset = _usable_reset_row(db, token_hash, for_update=True)
    if user is None or reset is None or reset.user_id != user.id:
        db.rollback()
        raise ResourceNotFoundError(_INVALID_TOKEN_MESSAGE)

    user.password_hash = password_hash
    # Backoff state is a DB-enforced pair: both reset together.
    user.failed_login_count = 0
    user.last_failed_login_at = None
    revoke_all_sessions(db, user_id=user.id)
    reset.used_at = func.now()
    recorder.record(
        db,
        AuditAction.AUTH_PASSWORD_RESET_COMPLETED,
        actor_user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        details=PasswordResetDetails(email_normalized=user.email_normalized),
    )
    db.commit()
