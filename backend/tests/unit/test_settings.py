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


class TestDatabaseUrlScheme:
    """ADR-007: only the synchronous psycopg 3 scheme is bootable."""

    def test_sync_psycopg_scheme_is_accepted(self) -> None:
        settings = build(database_url="postgresql+psycopg://u:p@localhost:5433/db")
        assert settings.database_url_str.startswith("postgresql+psycopg://")

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@localhost:5433/db",  # plain (driver-ambiguous)
            "postgres://u:p@localhost:5433/db",  # legacy plain
            "postgresql+asyncpg://u:p@localhost:5433/db",  # async driver
            "postgresql+psycopg2://u:p@localhost:5433/db",  # legacy driver
            "mysql://u:p@localhost:3306/db",  # unrelated database
            "https://example.com/db",  # unrelated scheme
        ],
    )
    def test_other_schemes_are_rejected(self, url: str) -> None:
        with pytest.raises(ValidationError):
            build(database_url=url)


class TestAppEnv:
    def test_defaults_to_development(self) -> None:
        assert build(database_url=VALID_URL).app_env is AppEnv.DEVELOPMENT

    def test_unknown_environment_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(app_env="staging", database_url=VALID_URL)

    def test_is_production_flag(self) -> None:
        production = build(
            app_env="production",
            database_url=VALID_URL,
            trusted_origins="https://admin.example.com",
            platform_base_domain="platform.example.com",
        )
        assert production.is_production
        assert not build(app_env="test", database_url=VALID_URL).is_production


class TestSessionSettings:
    """M2A session configuration (ADR-010)."""

    def test_defaults(self) -> None:
        settings = build(database_url=VALID_URL)
        assert settings.session_idle_timeout_minutes == 1440
        assert settings.session_absolute_lifetime_days == 30

    def test_nonpositive_lifetimes_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(database_url=VALID_URL, session_idle_timeout_minutes=0)
        with pytest.raises(ValidationError):
            build(database_url=VALID_URL, session_absolute_lifetime_days=0)

    def test_cookie_name_and_secure_flag_by_environment(self) -> None:
        development = build(database_url=VALID_URL)
        assert development.session_cookie_name == "session"
        assert development.session_cookie_secure is False

        production = build(
            app_env="production",
            database_url=VALID_URL,
            trusted_origins="https://admin.example.com",
            platform_base_domain="platform.example.com",
        )
        assert production.session_cookie_name == "__Host-session"
        assert production.session_cookie_secure is True


class TestTrustedOrigins:
    def test_default_is_the_dev_proxy_origin(self) -> None:
        assert build(database_url=VALID_URL).trusted_origin_set == frozenset(
            {"http://localhost:5173"}
        )

    def test_comma_separated_values_are_normalized(self) -> None:
        settings = build(
            database_url=VALID_URL,
            trusted_origins=" http://localhost:5173 , HTTP://testserver/ ,,",
        )
        assert settings.trusted_origin_set == frozenset(
            {"http://localhost:5173", "http://testserver"}
        )


class TestProductionConfigurationValidation:
    """A misconfigured production process must never start (ADR-010)."""

    def test_non_https_trusted_origin_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="https://"):
            build(app_env="production", database_url=VALID_URL)

    def test_empty_trusted_origins_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="TRUSTED_ORIGINS"):
            build(app_env="production", database_url=VALID_URL, trusted_origins=" , ")

    def test_placeholder_database_password_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="placeholder password"):
            build(
                app_env="production",
                database_url="postgresql+psycopg://u:restaurant_dev_only@db:5432/app",
                trusted_origins="https://admin.example.com",
            )

    def test_compliant_production_settings_are_accepted(self) -> None:
        settings = build(
            app_env="production",
            database_url="postgresql+psycopg://app:distinct-real-secret@db:5432/app",
            trusted_origins="https://admin.example.com,https://ops.example.com",
            platform_base_domain="platform.example.com",
        )
        assert settings.is_production

    def test_localhost_base_domain_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="PLATFORM_BASE_DOMAIN"):
            build(
                app_env="production",
                database_url="postgresql+psycopg://app:distinct-real-secret@db:5432/app",
                trusted_origins="https://admin.example.com",
            )

    def test_development_is_not_subject_to_production_checks(self) -> None:
        # The dev placeholder password and http origin are fine outside prod.
        settings = build(
            database_url="postgresql+psycopg://u:restaurant_dev_only@127.0.0.1:5433/db"
        )
        assert not settings.is_production


class TestPlatformBaseDomain:
    """M2C tenant-resolution base domain (ADR-013)."""

    def test_defaults_to_localhost_for_development(self) -> None:
        settings = build(database_url=VALID_URL)
        assert settings.platform_base_domain == "localhost"
        assert settings.platform_base_domain_labels == ("localhost",)

    def test_is_lowercased_and_split_into_labels(self) -> None:
        settings = build(database_url=VALID_URL, platform_base_domain="Platform.Example.COM")
        assert settings.platform_base_domain == "platform.example.com"
        assert settings.platform_base_domain_labels == ("platform", "example", "com")

    @pytest.mark.parametrize("value", ["127.0.0.1", "[::1]", "not a domain", "-bad.com", ""])
    def test_invalid_base_domain_is_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError, match="PLATFORM_BASE_DOMAIN"):
            build(database_url=VALID_URL, platform_base_domain=value)

    def test_one_trailing_root_dot_canonicalizes(self) -> None:
        settings = build(database_url=VALID_URL, platform_base_domain="platform.example.com.")
        assert settings.platform_base_domain == "platform.example.com"

    @pytest.mark.parametrize(
        "value",
        ["platform.example.com:8443", "localhost:8000", "platform.example.com:", "[::1]:8000"],
    )
    def test_base_domain_with_port_is_rejected_not_stripped(self, value: str) -> None:
        # Review finding R-3: the base domain is a DNS domain, not a request
        # authority — a port is a configuration error, never silently masked.
        with pytest.raises(ValidationError, match="must not contain a port"):
            build(database_url=VALID_URL, platform_base_domain=value)


class TestLogLevel:
    def test_defaults_to_info(self) -> None:
        assert build(database_url=VALID_URL).log_level == "INFO"

    def test_lowercase_input_is_normalized(self) -> None:
        assert build(database_url=VALID_URL, log_level="debug").log_level == "DEBUG"

    def test_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            build(database_url=VALID_URL, log_level="verbose")
