"""Shared test fixtures.

Non-integration tests construct explicit ``Settings`` (no environment or
`.env` coupling) and never require a running database: the SQLAlchemy engine
connects lazily, so building the app is safe without one.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from app.core.settings import AppEnv, Settings
from app.main import create_app

# 127.0.0.1, not localhost: the compose database binds only the IPv4
# loopback, and a dead ::1 attempt would add seconds to every connection.
TEST_DATABASE_URL = (
    "postgresql+psycopg://restaurant_dev:restaurant_dev_only@127.0.0.1:5433/restaurant_engine_test"
)


class ExplicitSettings(Settings):
    """Settings built from explicit values only.

    pydantic-settings applies environment and dotenv sources on every
    construction path (including ``model_validate``), so tests disable all
    implicit sources to stay deterministic on any developer machine.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def make_settings(**overrides: object) -> Settings:
    """Explicit test settings, isolated from env vars and .env files."""
    values: dict[str, object] = {
        "app_env": AppEnv.TEST,
        "database_url": TEST_DATABASE_URL,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return ExplicitSettings.model_validate(values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
