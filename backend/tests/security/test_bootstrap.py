"""Platform-admin bootstrap: service rules and CLI safety (M2A)."""

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.identity import service
from app.domains.identity.service import create_platform_admin, validate_and_normalize_email
from scripts import create_platform_admin as cli
from tests.conftest import TEST_DATABASE_URL
from tests.security.conftest import CreateUser, login


@pytest.fixture
def db(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as session:
        yield session


class TestCreatePlatformAdminService:
    def test_creates_admin_with_audit_event(self, db: Session, migrated_engine: Engine) -> None:
        user = create_platform_admin(
            db,
            email=" Admin@Example.com ",
            display_name="  Platform Admin  ",
            password="a-long-enough-password",
        )
        assert user.is_platform_admin
        assert user.email == "Admin@Example.com"
        with migrated_engine.connect() as connection:
            row = connection.execute(
                text("SELECT email_normalized, is_platform_admin FROM users")
            ).one()
            assert row.email_normalized == "admin@example.com"
            assert row.is_platform_admin is True
            actions = list(connection.execute(text("SELECT action FROM audit_events")).scalars())
        assert actions == ["user.platform_admin_created"]

    def test_password_policy_applies_when_setting(self, db: Session) -> None:
        with pytest.raises(ValueError, match="12-128"):
            create_platform_admin(db, email="a@b.co", display_name="A", password="tooshort")
        with pytest.raises(ValueError, match="12-128"):
            create_platform_admin(db, email="a@b.co", display_name="A", password="x" * 129)

    def test_duplicate_email_is_rejected(self, db: Session, create_user: CreateUser) -> None:
        create_user("taken@example.com")
        with pytest.raises(ValueError, match="already exists"):
            create_platform_admin(
                db, email="TAKEN@example.com", display_name="A", password="a-long-enough-password"
            )

    def test_created_admin_can_log_in(self, db: Session, client: TestClient) -> None:
        create_platform_admin(
            db, email="admin@example.com", display_name="A", password="a-long-enough-password"
        )
        response = login(client, email="admin@example.com", password="a-long-enough-password")
        assert response.status_code == 200
        assert response.json()["user"]["is_platform_admin"] is True


class TestEmailContract:
    """Bootstrap shares the HTTP layer's email contract (review LOW-1)."""

    @pytest.mark.parametrize(
        "bad_email",
        ["not-an-email", "missing-at.example.com", "two@@example.com", "a@b", ""],
    )
    def test_invalid_syntax_is_rejected_without_creating_a_user(
        self, db: Session, migrated_engine: Engine, bad_email: str
    ) -> None:
        with pytest.raises(ValueError, match="invalid email"):
            create_platform_admin(
                db, email=bad_email, display_name="A", password="a-long-enough-password"
            )
        with migrated_engine.connect() as connection:
            count = connection.execute(text("SELECT count(*) FROM users")).scalar()
        assert count == 0

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        display, normalized = validate_and_normalize_email("  Owner@Example.COM  ")
        assert display == "Owner@Example.COM"
        assert normalized == "owner@example.com"

    def test_case_is_normalized_for_identity_only(self, db: Session, client: TestClient) -> None:
        create_platform_admin(
            db, email="MiXeD@Example.com", display_name="A", password="a-long-enough-password"
        )
        # Identity is the normalized form; display keeps the entered case.
        response = login(client, email="mixed@example.com", password="a-long-enough-password")
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "MiXeD@Example.com"

    def test_valid_email_passes(self) -> None:
        display, normalized = validate_and_normalize_email("owner+tag@sub.example.co")
        assert display == "owner+tag@sub.example.co"
        assert normalized == "owner+tag@sub.example.co"


class TestDuplicateRace:
    """The check-then-insert race resolves cleanly (review LOW-2)."""

    def test_unique_violation_converts_to_the_duplicate_error(
        self,
        db: Session,
        create_user: CreateUser,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Simulate losing the race: the pre-check sees no user, but the row
        # exists by insert time, so uq_users_email_normalized fires.
        create_user("raced@example.com")
        monkeypatch.setattr(service, "_email_exists", lambda *_args, **_kwargs: False)
        with pytest.raises(ValueError, match="already exists"):
            create_platform_admin(
                db,
                email="raced@example.com",
                display_name="A",
                password="a-long-enough-password",
            )
        # The failed transaction was rolled back: the session is usable.
        assert db.execute(text("SELECT 1")).scalar() == 1

    def test_unrelated_integrity_errors_propagate(self, db: Session) -> None:
        # An all-whitespace display name strips to '' and violates
        # ck_users_display_name_length — not the duplicate constraint, so
        # it must surface as IntegrityError, never the duplicate message.
        with pytest.raises(IntegrityError):
            create_platform_admin(
                db,
                email="ok@example.com",
                display_name="   ",
                password="a-long-enough-password",
            )


class TestCli:
    def test_password_stdin_path_creates_the_admin(
        self,
        monkeypatch: pytest.MonkeyPatch,
        migrated_engine: Engine,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Process env outranks .env in pydantic-settings: the CLI runs
        # against the test database, never the developer database.
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        monkeypatch.setattr("sys.stdin", io.StringIO("a-long-enough-password\n"))

        cli.main(["--email", "cli@example.com", "--display-name", "CLI Admin", "--password-stdin"])

        output = capsys.readouterr().out
        assert "created platform admin cli@example.com" in output
        assert "a-long-enough-password" not in output
        with migrated_engine.connect() as connection:
            count = connection.execute(
                text("SELECT count(*) FROM users WHERE is_platform_admin")
            ).scalar()
        assert count == 1

    def test_mismatched_interactive_passwords_abort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = iter(["first-password-value", "second-password-value"])
        monkeypatch.setattr("getpass.getpass", lambda _prompt: next(answers))
        with pytest.raises(SystemExit):
            cli.main(["--email", "x@y.co", "--display-name", "X"])

    def test_policy_violation_exits_nonzero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
        with pytest.raises(SystemExit):
            cli.main(["--email", "x@y.co", "--display-name", "X", "--password-stdin"])
        assert "12-128" in capsys.readouterr().err

    def test_no_password_argument_exists(self) -> None:
        # argv leaks into shell history/process listings; the flag must
        # never exist (approved review item R13).
        with pytest.raises(SystemExit):
            cli.main(["--email", "x@y.co", "--display-name", "X", "--password", "leaky-password!"])
