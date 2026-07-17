"""Structured application settings with fail-fast validation.

Settings are read from the process environment first, then from a local
`.env` file (development convenience; `.env` is gitignored). Every variable
consumed here must have a safe placeholder in the repository-root
`.env.example` (docs/05).
"""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development placeholders that must never reach production (blueprint §11.2:
# production startup fails when insecure example secrets are detected).
_PLACEHOLDER_DB_PASSWORDS = frozenset({"restaurant_dev_only", "export", "postgres", "password"})

# The canonical .env lives at the repository root (docs/05), next to
# .env.example. Anchored on this file's location so backend commands work
# from any working directory.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class AppEnv(StrEnum):
    """Deployment environment the application believes it is running in."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Validated application configuration.

    Instantiation fails immediately when a required variable is missing or
    malformed, so a misconfigured process never starts serving traffic.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    database_url: PostgresDsn
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Sessions and browser security (M2A, ADR-010) ----------------------
    # Server-side session validity: both bounds are enforced on every
    # authenticated request; the cookie's Max-Age mirrors the absolute bound.
    session_idle_timeout_minutes: int = Field(default=1440, ge=1)  # 24 hours
    session_absolute_lifetime_days: int = Field(default=30, ge=1)
    # Comma-separated exact origins allowed to originate browser-facing
    # unsafe requests (fail-closed CSRF check, ADR-010). Same-origin
    # consumption is the deployment contract; this list exists for the dev
    # proxy origin and for test clients.
    trusted_origins: str = "http://localhost:5173"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("database_url")
    @classmethod
    def _require_sync_psycopg_scheme(cls, value: PostgresDsn) -> PostgresDsn:
        # ADR-007: the backend runs synchronous SQLAlchemy on psycopg 3.
        # Rejecting every other scheme (plain postgresql, asyncpg, psycopg2)
        # at startup prevents a misconfigured process from booting on the
        # wrong driver.
        if value.scheme != "postgresql+psycopg":
            msg = (
                "DATABASE_URL must use the 'postgresql+psycopg' scheme "
                f"(ADR-007 sync psycopg 3 driver); got '{value.scheme}'"
            )
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_production_configuration(self) -> "Settings":
        """Refuse to start a misconfigured production process (ADR-010)."""
        if self.app_env is not AppEnv.PRODUCTION:
            return self
        problems: list[str] = []
        if not self.trusted_origin_set:
            problems.append("TRUSTED_ORIGINS must not be empty in production")
        for origin in self.trusted_origin_set:
            if not origin.startswith("https://"):
                problems.append(f"trusted origin '{origin}' must use https:// in production")
        passwords = {host.get("password") or "" for host in self.database_url.hosts()}
        if passwords & _PLACEHOLDER_DB_PASSWORDS:
            problems.append("DATABASE_URL uses a known development placeholder password")
        if problems:
            raise ValueError("; ".join(sorted(problems)))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)

    @property
    def trusted_origin_set(self) -> frozenset[str]:
        """Normalized (lowercased, no trailing slash) exact trusted origins."""
        return frozenset(
            origin.strip().rstrip("/").lower()
            for origin in self.trusted_origins.split(",")
            if origin.strip()
        )

    @property
    def session_cookie_name(self) -> str:
        # __Host- binds the cookie to the exact host, requires Secure and
        # Path=/ with no Domain attribute — free hardening, production only
        # because the prefix is invalid over plain HTTP (ADR-010).
        return "__Host-session" if self.is_production else "session"

    @property
    def session_cookie_secure(self) -> bool:
        return self.is_production


def load_settings() -> Settings:
    """Build settings from the environment (and `.env` when present)."""
    # Required fields are supplied by the environment at runtime; mypy cannot
    # see that, hence the targeted ignore.
    return Settings()  # type: ignore[call-arg]
