"""Identity domain errors (M2A, ADR-010).

Both render through the central ApiError handler. Login failure is
deliberately one exception with one message: unknown email, wrong
password, inactive account, and throttled attempts are indistinguishable
to the client (existence non-disclosure).
"""

from fastapi import status

from app.core.errors import ApiError, ErrorCode

# One uniform message for every login-failure path.
_INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."


class InvalidCredentialsError(ApiError):
    def __init__(self) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.INVALID_CREDENTIALS,
            _INVALID_CREDENTIALS_MESSAGE,
        )


class AuthenticationRequiredError(ApiError):
    """No valid session on a route that needs one.

    ``headers`` lets the HTTP layer attach a session-cookie deletion when
    the client presented a cookie that turned out invalid (ADR-010).
    """

    def __init__(self, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.AUTHENTICATION_REQUIRED,
            "Authentication required.",
            headers=headers,
        )
