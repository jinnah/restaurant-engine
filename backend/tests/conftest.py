"""Shared test fixtures.

Non-integration tests construct explicit ``Settings`` (no environment or
`.env` coupling) and never require a running database: the SQLAlchemy engine
connects lazily, so building the app is safe without one.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core.settings import AppEnv, Settings
from app.main import create_app

# A process-wide temporary media root so no test ever writes into the
# gitignored development media root (backend/var/media). Created once and
# reused; the OS reclaims it after the run.
_TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="re-test-media-"))

# 127.0.0.1, not localhost: the compose database binds only the IPv4
# loopback, and a dead ::1 attempt would add seconds to every connection.
TEST_DATABASE_URL = (
    "postgresql+psycopg://restaurant_dev:restaurant_dev_only@127.0.0.1:5433/restaurant_engine_test"
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Ensure the isolated test database exists; fail clearly when down.

    Used by tests/integration/ and tests/security/ (both carry the
    ``integration`` marker via their conftest hooks).
    """
    url = make_url(TEST_DATABASE_URL)
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3}
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    except OperationalError as exc:
        pytest.fail(
            "PostgreSQL is not reachable on 127.0.0.1:5433. "
            "Start it with `docker compose up -d db` from the repository root. "
            f"Underlying error: {type(exc).__name__}",
            pytrace=False,
        )
    finally:
        admin_engine.dispose()
    return TEST_DATABASE_URL


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
        # Never the development media root; a throwaway temp directory.
        "media_storage_root": str(_TEST_MEDIA_ROOT),
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
