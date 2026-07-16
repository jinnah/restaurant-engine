"""Password hashing and opaque-token primitives (M2A, ADR-010).

Argon2id parameters are explicit, reviewed constants — never library
defaults, so an upstream default change can not silently weaken hashing.
Profile: RFC 9106 low-memory (64 MiB, t=3) with parallelism=1 because the
production target is a 1-2 vCPU VPS where per-hash thread fan-out hurts
under concurrent logins.

Acceptance criterion (ADR-010): ``verify`` takes 100-500 ms on the
production VPS, measured with ``scripts.benchmark_password_hashing`` and
re-checked in the Milestone 8 deployment runbook. Out-of-window results
trigger a parameter-change ADR; ``password_needs_rehash`` upgrades stored
hashes transparently on the next successful login.

Session and CSRF tokens are 256-bit URL-safe random values. Session tokens
are stored only as SHA-256 hex digests: lookup needs a deterministic hash,
and a KDF adds nothing against offline attack of a 256-bit random value.
"""

import hashlib
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# --- Argon2id parameters (explicit contract, ADR-010) -----------------------

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KIB = 65536  # 64 MiB
ARGON2_PARALLELISM = 1
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16

# Applies when *setting* a password (bootstrap now; reset/invitations later).
# Login verification accepts any length: policy changes must never lock out
# accounts created under an older policy.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST_KIB,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LENGTH,
    salt_len=ARGON2_SALT_LENGTH,
)


def hash_password(password: str) -> str:
    """Hash a password with the explicit Argon2id parameters."""
    return _hasher.hash(password)


def verify_password(password_hash: str, candidate: str) -> bool:
    """Constant-decision verification: True only on an exact match."""
    try:
        return _hasher.verify(password_hash, candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current explicit parameters."""
    return _hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    # Computed lazily with the *current* parameters so the dummy path always
    # costs exactly what a real verification costs. The hashed value is
    # random per process and never matches any submitted password.
    return hash_password(secrets.token_urlsafe(32))


def verify_dummy_password(candidate: str) -> None:
    """Burn one real Argon2 verification without an account.

    Called on the unknown-email, inactive-account, and throttled login paths
    so their timing is indistinguishable from a wrong-password attempt
    (ADR-010).
    """
    verify_password(_dummy_password_hash(), candidate)


# --- Opaque tokens (sessions, CSRF; single-use tokens from M2D) -------------


def generate_opaque_token() -> str:
    """256-bit URL-safe random token (session, CSRF, future one-time links)."""
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """Deterministic storage form of an opaque token (SHA-256 hex)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
