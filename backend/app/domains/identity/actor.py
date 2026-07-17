"""Resolved-principal value types (M2A/M2B).

Extracted into their own dependency-light module so the capability policy
(``identity.policies``) and any consumer can use them without importing the
identity service (which pulls in security, audit, and the ORM). Behavior is
unchanged from M2A; only the definition site moved.
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class AuthenticatedUser:
    """Snapshot of the authenticated user for response building."""

    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool


@dataclass(frozen=True)
class ActorContext:
    """Resolved request actor: who is calling, on which session."""

    user: AuthenticatedUser
    session_id: uuid.UUID
    csrf_token: str
