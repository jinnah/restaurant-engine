"""Structured application settings with fail-fast validation.

Settings are read from the process environment first, then from a local
`.env` file (development convenience; `.env` is gitignored). Every variable
consumed here must have a safe placeholder in the repository-root
`.env.example` (docs/05).
"""

from enum import StrEnum
from typing import Literal

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    database_url: PostgresDsn
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def database_url_str(self) -> str:
        return str(self.database_url)


def load_settings() -> Settings:
    """Build settings from the environment (and `.env` when present)."""
    # Required fields are supplied by the environment at runtime; mypy cannot
    # see that, hence the targeted ignore.
    return Settings()  # type: ignore[call-arg]
