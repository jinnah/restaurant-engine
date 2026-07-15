"""Shared test fixtures.

Non-integration tests construct explicit ``Settings`` (no environment or
`.env` coupling) and never require a running database: the SQLAlchemy engine
connects lazily, so building the app is safe without one.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.settings import AppEnv, Settings
from app.main import create_app

TEST_DATABASE_URL = (
    "postgresql+psycopg://restaurant_dev:restaurant_dev_only@localhost:5433/restaurant_engine_test"
)


def make_settings(**overrides: object) -> Settings:
    """Explicit test settings, isolated from the process environment."""
    values: dict[str, object] = {
        "app_env": AppEnv.TEST,
        "database_url": TEST_DATABASE_URL,
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
