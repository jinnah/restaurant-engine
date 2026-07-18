"""Identity API schemas (M2A).

Commands reject unknown fields (blueprint §11.3: strict input schemas).
Response schemas are explicit — never serialized ORM objects (docs/02).
The session payload gains a ``memberships`` field in Milestone 2B,
additively.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    # Login accepts any non-empty password: length policy applies when
    # *setting* passwords, never when verifying (app.core.security).
    password: str = Field(min_length=1, max_length=1024)


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_platform_admin: bool


class SessionResponse(BaseModel):
    """Current authenticated identity plus the CSRF synchronizer token."""

    user: UserSummary
    csrf_token: str


class LogoutResponse(BaseModel):
    status: Literal["logged_out"]


class PasswordResetIssueRequest(BaseModel):
    """Platform command: issue a reset token for an account (M2D)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)


class PasswordResetIssueResponse(BaseModel):
    """One-time issuance result (ADR-014).

    ``token`` is the raw secret, returned exactly once to the authorized
    issuer for out-of-band delivery — never a URL, never stored, never
    logged, never shown again.
    """

    token: str
    expires_at: datetime
    email: str


class PasswordResetRedeemRequest(BaseModel):
    """Public command: redeem a reset token and set a new password (M2D)."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=128)
    # Password policy applies when *setting* passwords (docs/03).
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class PasswordResetRedeemResponse(BaseModel):
    status: Literal["password_reset"]
