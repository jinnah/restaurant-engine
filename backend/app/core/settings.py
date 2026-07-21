"""Structured application settings with fail-fast validation.

Settings are read from the process environment first, then from a local
`.env` file (development convenience; `.env` is gitignored). Every variable
consumed here must have a safe placeholder in the repository-root
`.env.example` (docs/05).
"""

from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.hosts import normalize_host

# M3C media upload cap bounds (ADR-017 R2). The default is the safe
# floor; deployments may raise it up to the maximum. This is the one
# deployment-tunable media limit — quotas and pixel bounds are code policy.
_DEFAULT_UPLOAD_MAX_BYTES = 10_485_760  # 10 MiB
_MAX_UPLOAD_MAX_BYTES = 20_971_520  # 20 MiB

# The development-only default media storage root (gitignored). Production
# must set an explicit durable absolute path (validated below). Stored as a
# string so absoluteness is judged on the literal configured value, not on
# a host-OS-coerced Path (a POSIX production path must validate even when
# the config is checked on a Windows developer machine).
_DEV_MEDIA_ROOT = str(Path(__file__).resolve().parents[2] / "var" / "media")

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

    # --- Tenant resolution (M2C, ADR-013) ----------------------------------
    # The platform base domain. A public request whose Host is a direct
    # subdomain of this domain resolves that subdomain label to a Business
    # slug. Development uses ``localhost`` so ``{slug}.localhost`` resolves;
    # production must set a real domain (validated below). Infrastructure
    # labels (api/admin/www) are the reserved-slug set and are never tenants.
    platform_base_domain: str = "localhost"

    # --- Onboarding and recovery tokens (M2D, ADR-014) ---------------------
    # Single-use token lifetimes. Both are decided on the DATABASE clock:
    # expires_at is computed in SQL at insert and validity always compares
    # against now() in SQL, so application-clock skew cannot change an
    # expiry decision. Bounds keep a typo from minting near-immortal tokens.
    invitation_expiry_days: int = Field(default=7, ge=1, le=30)
    password_reset_expiry_minutes: int = Field(default=60, ge=5, le=1440)

    # --- Media storage (M3C, ADR-017) --------------------------------------
    # The filesystem root for stored media objects. Development defaults to
    # a gitignored path inside the repo; production must set an explicit
    # durable absolute directory outside any static-served path (validated
    # below, and probed at startup by the media storage adapter). Held as a
    # string; use ``media_storage_root_path`` for a Path.
    media_storage_root: str = _DEV_MEDIA_ROOT
    # The uploaded-file size cap (the file payload, not multipart overhead).
    # The one deployment-tunable media limit; bounded 10-20 MiB (R2).
    media_upload_max_bytes: int = Field(
        default=_DEFAULT_UPLOAD_MAX_BYTES,
        ge=_DEFAULT_UPLOAD_MAX_BYTES,
        le=_MAX_UPLOAD_MAX_BYTES,
    )

    @field_validator("platform_base_domain")
    @classmethod
    def _valid_base_domain(cls, value: str) -> str:
        # The base domain is a DNS domain, not a request authority: a port
        # (or any colon — bracketed IPv6 included) is a configuration error
        # and must fail startup rather than be silently stripped.
        if ":" in value:
            msg = f"PLATFORM_BASE_DOMAIN must not contain a port; got {value!r}"
            raise ValueError(msg)
        # Reuse the Host parser: the base domain must be a valid DNS hostname
        # (never an IP literal), stored in canonical lowercase form (case and
        # one trailing root dot canonicalize; anything else fails).
        normalized = normalize_host(value)
        if normalized is None or normalized.is_ip:
            msg = f"PLATFORM_BASE_DOMAIN must be a valid DNS hostname; got {value!r}"
            raise ValueError(msg)
        return normalized.hostname

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
        if self.platform_base_domain == "localhost":
            problems.append(
                "PLATFORM_BASE_DOMAIN must be a real domain (not localhost) in production"
            )
        # Media root (M3C): production must set an explicit, absolute,
        # durable path — never the repo-local development default inside an
        # ephemeral container. Existence and writability are probed at
        # startup by the storage adapter (not here, to keep settings pure).
        if self.media_storage_root == _DEV_MEDIA_ROOT:
            problems.append(
                "MEDIA_STORAGE_ROOT must be set to an explicit durable path in production"
            )
        else:
            # Absoluteness is judged cross-platform on the literal configured
            # string: the deployment target is Linux (POSIX paths), but
            # validation may run on the config author's Windows machine.
            raw = self.media_storage_root
            if not (PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).is_absolute()):
                problems.append("MEDIA_STORAGE_ROOT must be an absolute path in production")
        if problems:
            raise ValueError("; ".join(sorted(problems)))
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def media_storage_root_path(self) -> Path:
        """The configured media root as a Path (M3C)."""
        return Path(self.media_storage_root)

    @property
    def platform_base_domain_labels(self) -> tuple[str, ...]:
        """The base domain as normalized DNS labels (M2C resolution)."""
        return tuple(self.platform_base_domain.split("."))

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
