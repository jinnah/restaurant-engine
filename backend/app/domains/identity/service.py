"""Identity application service (M2A, ADR-010).

Owns every login/logout/session-validation workflow and its transaction
boundary (docs/02: services orchestrate and commit; repositories/HTTP do
not). Three properties are load-bearing:

* **Uniform failure.** Unknown email, wrong password, inactive account,
  and throttled attempts all raise the same ``InvalidCredentialsError``
  after committing their side effects; Argon2 work is performed on every
  path (dummy verification where no real hash applies) so timing does not
  disclose account state.
* **Failure commits are deliberate.** A rejected login is a normal domain
  outcome, not an exception unwinding a transaction: counter updates and
  audit events are committed *before* the failure is raised.
* **KDF outside transactions.** Password verification takes ~hundreds of
  milliseconds by design; the read transaction is closed before verifying
  so no database state is held open across it.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.settings import Settings
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    LoginFailedDetails,
    LoginThrottledDetails,
    PlatformAdminCreatedDetails,
)
from app.domains.identity import throttling
from app.domains.identity.actor import ActorContext, AuthenticatedUser
from app.domains.identity.exceptions import InvalidCredentialsError
from app.domains.identity.models import User, UserSession

# Refreshing sessions.last_used_at on every request would write-amplify;
# one refresh per minute bounds idle-tracking error at 60s, which is noise
# against a 24h idle window (ADR-010).
_LAST_USED_REFRESH_SECONDS = 60


def normalize_email(email: str) -> str:
    """Canonical account identity: trimmed and lowercased."""
    return email.strip().lower()


def validate_and_normalize_email(email: str) -> tuple[str, str]:
    """Shared email contract for non-HTTP account creation paths.

    Applies the same validation the HTTP layer gets from ``EmailStr``
    (email-validator syntax checks, deliverability/network checks
    disabled) plus this project's normalization. Returns
    ``(display_email, email_normalized)``; raises ``ValueError`` with an
    operator-readable message on invalid syntax (security review M2A,
    LOW-1).
    """
    candidate = email.strip()
    try:
        validate_email(candidate, check_deliverability=False)
    except EmailNotValidError as exc:
        msg = f"invalid email address: {exc}"
        raise ValueError(msg) from None
    return candidate, normalize_email(candidate)


@dataclass(frozen=True)
class LoginResult:
    user: AuthenticatedUser
    session_token: str  # raw opaque token: sent as the cookie, never stored
    csrf_token: str


@dataclass(frozen=True)
class _UserSnapshot:
    """Plain-value copy of the account row, safe to use after rollback."""

    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool
    is_active: bool
    password_hash: str
    failed_login_count: int
    last_failed_login_at: datetime | None


def _load_user_snapshot(db: Session, email_normalized: str) -> _UserSnapshot | None:
    user = db.execute(
        select(User).where(User.email_normalized == email_normalized)
    ).scalar_one_or_none()
    if user is None:
        return None
    return _UserSnapshot(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        is_active=user.is_active,
        password_hash=user.password_hash,
        failed_login_count=user.failed_login_count,
        last_failed_login_at=user.last_failed_login_at,
    )


_FailureReason = Literal["unknown_email", "invalid_password", "inactive_account"]


def _fail_login(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    email_normalized: str,
    reason: _FailureReason,
    count_failure_for: uuid.UUID | None = None,
) -> InvalidCredentialsError:
    """Commit failure side effects, return the uniform error to raise."""
    if count_failure_for is not None:
        # Single-statement increment: concurrency-safe, no read-modify-write
        # (approved addendum item 1). now() evaluates in the database so the
        # count/timestamp pairing CK can never be broken by clock skew.
        db.execute(
            update(User)
            .where(User.id == count_failure_for)
            .values(
                failed_login_count=User.failed_login_count + 1,
                last_failed_login_at=func.now(),
            )
        )
    recorder.record(
        db,
        AuditAction.AUTH_LOGIN_FAILED,
        actor_user_id=actor_user_id,
        details=LoginFailedDetails(email_normalized=email_normalized, reason=reason),
    )
    db.commit()
    return InvalidCredentialsError()


def login(db: Session, settings: Settings, *, email: str, password: str) -> LoginResult:
    """Authenticate and open a fresh session (rotation-by-construction).

    Raises ``InvalidCredentialsError`` uniformly on every failure path;
    side effects (backoff counter, audit events) are committed first.
    """
    email_normalized = normalize_email(email)
    snapshot = _load_user_snapshot(db, email_normalized)
    # Close the read transaction before any KDF work (module docstring).
    db.rollback()

    if snapshot is None:
        security.verify_dummy_password(password)
        raise _fail_login(
            db,
            actor_user_id=None,
            email_normalized=email_normalized,
            reason="unknown_email",
        )

    if throttling.is_throttled(snapshot.failed_login_count, snapshot.last_failed_login_at):
        # Inside the backoff window the real hash is never consulted —
        # otherwise backoff would not slow guessing at all. The counter is
        # not touched: attempts must not extend the window (addendum item 1).
        security.verify_dummy_password(password)
        recorder.record(
            db,
            AuditAction.AUTH_LOGIN_THROTTLED,
            actor_user_id=snapshot.id,
            details=LoginThrottledDetails(
                email_normalized=email_normalized,
                failed_login_count=snapshot.failed_login_count,
                backoff_seconds=throttling.required_backoff_seconds(snapshot.failed_login_count),
            ),
        )
        db.commit()
        raise InvalidCredentialsError()

    if not snapshot.is_active:
        security.verify_dummy_password(password)
        raise _fail_login(
            db,
            actor_user_id=snapshot.id,
            email_normalized=email_normalized,
            reason="inactive_account",
        )

    if not security.verify_password(snapshot.password_hash, password):
        raise _fail_login(
            db,
            actor_user_id=snapshot.id,
            email_normalized=email_normalized,
            reason="invalid_password",
            count_failure_for=snapshot.id,
        )

    # --- Success: one transaction for reset + session + audit --------------
    now = datetime.now(UTC)
    success_values: dict[str, object] = {
        "failed_login_count": 0,
        "last_failed_login_at": None,
    }
    if security.password_needs_rehash(snapshot.password_hash):
        # Transparent parameter upgrade (ADR-010).
        success_values["password_hash"] = security.hash_password(password)
    db.execute(update(User).where(User.id == snapshot.id).values(**success_values))

    # Opportunistic hygiene: this user's dead sessions go now (ADR-010).
    idle_cutoff = now - timedelta(minutes=settings.session_idle_timeout_minutes)
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == snapshot.id,
            or_(
                UserSession.revoked_at.is_not(None),
                UserSession.absolute_expires_at <= now,
                UserSession.last_used_at <= idle_cutoff,
            ),
        )
    )

    session_token = security.generate_opaque_token()
    csrf_token = security.generate_opaque_token()
    db.add(
        UserSession(
            user_id=snapshot.id,
            token_hash=security.hash_opaque_token(session_token),
            csrf_token=csrf_token,
            created_at=now,
            last_used_at=now,
            absolute_expires_at=now + timedelta(days=settings.session_absolute_lifetime_days),
        )
    )
    recorder.record(db, AuditAction.AUTH_LOGIN_SUCCEEDED, actor_user_id=snapshot.id)
    db.commit()

    return LoginResult(
        user=AuthenticatedUser(
            id=snapshot.id,
            email=snapshot.email,
            display_name=snapshot.display_name,
            is_platform_admin=snapshot.is_platform_admin,
        ),
        session_token=session_token,
        csrf_token=csrf_token,
    )


def resolve_session(db: Session, settings: Settings, *, session_token: str) -> ActorContext | None:
    """Validate a presented session token; None means 'treat as no session'.

    Validity (ADR-010): session not revoked, inside the absolute bound,
    inside the idle window, and the owning user still active. Authorization
    state is *always* read fresh from the database — sessions cache nothing,
    so privilege changes take effect on the next request.
    """
    now = datetime.now(UTC)
    token_hash = security.hash_opaque_token(session_token)
    row = db.execute(
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(UserSession.token_hash == token_hash)
    ).first()
    if row is None:
        return None
    user_session: UserSession = row[0]
    user: User = row[1]

    idle_cutoff = now - timedelta(minutes=settings.session_idle_timeout_minutes)
    if (
        user_session.revoked_at is not None
        or user_session.absolute_expires_at <= now
        or user_session.last_used_at <= idle_cutoff
        or not user.is_active
    ):
        return None

    if now - user_session.last_used_at > timedelta(seconds=_LAST_USED_REFRESH_SECONDS):
        # Infrastructure write, deliberately committed here: idle tracking
        # is session bookkeeping, not part of any business transaction.
        db.execute(
            update(UserSession).where(UserSession.id == user_session.id).values(last_used_at=now)
        )
        db.commit()

    return ActorContext(
        user=AuthenticatedUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_platform_admin=user.is_platform_admin,
        ),
        session_id=user_session.id,
        csrf_token=user_session.csrf_token,
    )


def logout(db: Session, *, actor: ActorContext) -> None:
    """Revoke the current session (idempotent) and audit the logout."""
    db.execute(
        update(UserSession)
        .where(UserSession.id == actor.session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    recorder.record(db, AuditAction.AUTH_LOGOUT, actor_user_id=actor.user.id)
    db.commit()


def revoke_all_sessions(db: Session, *, user_id: uuid.UUID) -> int:
    """Revoke every live session of a user; returns the count revoked.

    Participates in the caller's transaction (no commit): the caller
    couples it to the privilege change that requires it — password reset
    and account deactivation from M2D (ADR-010).
    """
    result = db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return cast("CursorResult[Any]", result).rowcount


def _email_exists(db: Session, email_normalized: str) -> bool:
    return (
        db.execute(
            select(User.id).where(User.email_normalized == email_normalized)
        ).scalar_one_or_none()
        is not None
    )


def find_user_id_by_email(db: Session, *, email_normalized: str) -> uuid.UUID | None:
    """The account id for a normalized email, or None (M2D, ADR-014).

    Narrow read for the businesses onboarding service (already-a-member and
    registered-since-issuance checks). The caller must never let this
    lookup's outcome change an unauthenticated response shape — account
    existence is not disclosed publicly.
    """
    return db.execute(
        select(User.id).where(User.email_normalized == email_normalized)
    ).scalar_one_or_none()


def create_user_from_invitation(
    db: Session, *, email: str, email_normalized: str, display_name: str, password_hash: str
) -> uuid.UUID:
    """Add a member account inside the caller's transaction (M2D, ADR-014).

    Identity remains the sole owner of user writes; the businesses
    onboarding service calls this during invitation acceptance. The Argon2
    hash is computed by the caller *before* its write transaction (two-phase
    design) and arrives ready to store. Never commits; never auto-logs-in.
    The email unique constraint backstops the registered-since-issuance
    race; the caller converts that ``IntegrityError`` into its uniform
    invalid-token response.
    """
    user = User(
        email=email,
        email_normalized=email_normalized,
        display_name=display_name.strip(),
        password_hash=password_hash,
        is_platform_admin=False,
    )
    db.add(user)
    db.flush()
    return user.id


def _is_email_unique_violation(exc: IntegrityError) -> bool:
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == "uq_users_email_normalized"


def create_platform_admin(
    db: Session, *, email: str, display_name: str, password: str
) -> AuthenticatedUser:
    """Create a platform administrator (bootstrap CLI only in M2A).

    Password policy is enforced here (setting a password), never at login;
    the email contract matches the HTTP layer (validate_and_normalize_email).
    Raises ``ValueError`` on policy violations or duplicate email so the
    CLI can present them; commits on success. The check-then-insert race is
    closed by ``uq_users_email_normalized``: that one violation is rolled
    back and converted to the same duplicate ``ValueError``; every other
    ``IntegrityError`` is rolled back and propagates (security review M2A,
    LOW-2).
    """
    if not (security.PASSWORD_MIN_LENGTH <= len(password) <= security.PASSWORD_MAX_LENGTH):
        msg = (
            f"password must be {security.PASSWORD_MIN_LENGTH}-"
            f"{security.PASSWORD_MAX_LENGTH} characters"
        )
        raise ValueError(msg)
    display_email, email_normalized = validate_and_normalize_email(email)
    duplicate_msg = f"a user with email '{email_normalized}' already exists"
    if _email_exists(db, email_normalized):
        raise ValueError(duplicate_msg)

    user = User(
        email=display_email,
        email_normalized=email_normalized,
        display_name=display_name.strip(),
        password_hash=security.hash_password(password),
        is_platform_admin=True,
    )
    db.add(user)
    try:
        db.flush()  # assign defaults before auditing the id
    except IntegrityError as exc:
        db.rollback()
        if _is_email_unique_violation(exc):
            raise ValueError(duplicate_msg) from None
        raise
    recorder.record(
        db,
        AuditAction.USER_PLATFORM_ADMIN_CREATED,
        actor_user_id=None,
        target_type="user",
        target_id=str(user.id),
        details=PlatformAdminCreatedDetails(email_normalized=email_normalized),
    )
    db.commit()
    return AuthenticatedUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=True,
    )
