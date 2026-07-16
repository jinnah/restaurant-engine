"""Identity API schemas (M2A).

Commands reject unknown fields (blueprint §11.3: strict input schemas).
Response schemas are explicit — never serialized ORM objects (docs/02).
The session payload gains a ``memberships`` field in Milestone 2B,
additively.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
