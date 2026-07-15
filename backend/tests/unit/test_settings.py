"""Settings validation behavior (via ExplicitSettings: implicit sources
disabled, see tests/conftest.py)."""

import pytest
from pydantic import ValidationError

from app.core.settings import AppEnv, Settings
from tests.conftest import ExplicitSettings

VALID_URL = "postgresql+psycopg://user:pw@localhost:5433/db"


def build(**values: object) -> Settings:
    """Construct settings from explicit values only."""
    return ExplicitSettings.model_validate(values)


class TestRequiredConfiguration:
    def test_database_url_is_required(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            build(app_env="test")
        assert any(e["loc"] == ("database_url",) for e in excinfo.value.errors())

    def test_malformed_database_url_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(app_env="test", database_url="not-a-database-url")


class TestAppEnv:
    def test_defaults_to_development(self) -> None:
        assert build(database_url=VALID_URL).app_env is AppEnv.DEVELOPMENT

    def test_unknown_environment_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(app_env="staging", database_url=VALID_URL)

    def test_is_production_flag(self) -> None:
        assert build(app_env="production", database_url=VALID_URL).is_production
        assert not build(app_env="test", database_url=VALID_URL).is_production


class TestLogLevel:
    def test_defaults_to_info(self) -> None:
        assert build(database_url=VALID_URL).log_level == "INFO"

    def test_lowercase_input_is_normalized(self) -> None:
        assert build(database_url=VALID_URL, log_level="debug").log_level == "DEBUG"

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(database_url=VALID_URL, log_level="verbose")
