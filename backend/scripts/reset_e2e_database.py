"""Create, migrate, or drop the disposable E2E database (M2F, ADR-016).

The ONLY target this script will ever touch is ``restaurant_engine_e2e``
on the canonical compose/CI server ``127.0.0.1:5433``. Every URL
component — driver, host, explicit port, database name, and the absence
of query parameters — is validated against exact literals BEFORE any
connection is opened or any SQL runs: the development database, the
standing test database, remote or aliased hosts, libpq ``?host=``/
``?port=`` overrides, Unix sockets, and anything else unexpected are
hard refusals (exit 2). The E2E orchestrator constructs the canonical
URL itself; an inherited or hand-typed ``DATABASE_URL`` cannot redirect
the operation.

Usage (the E2E orchestrator is the intended caller)::

    DATABASE_URL=postgresql+psycopg://...:5433/restaurant_engine_e2e \
        uv run --directory backend python -m scripts.reset_e2e_database --recreate
    ... --drop

``--recreate`` drops any stale E2E database, creates it fresh, and
migrates to the Alembic head; if migration fails, the half-made database
is dropped again before the error propagates, so a failed run leaves
nothing behind. ``--drop`` removes it.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

E2E_DATABASE_NAME = "restaurant_engine_e2e"
# The single canonical server (the compose/CI PostgreSQL): destructive
# operations are refused anywhere else. `localhost` is deliberately not
# accepted — one canonical spelling, no resolution ambiguity.
E2E_SERVER_DRIVER = "postgresql+psycopg"
E2E_SERVER_HOST = "127.0.0.1"
E2E_SERVER_PORT = 5433
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _refuse(reason: str) -> NoReturn:
    print(f"error: {reason}", file=sys.stderr)
    raise SystemExit(2)


def _validated_url() -> URL:
    """The target URL, hard-refused unless every component is canonical.

    The allowlist covers the full target, not just the database name:
    exact driver, exact loopback host, exact port, and zero query
    parameters — a libpq `?host=`/`?port=` override, a multi-host list,
    a Unix-socket path, or any other libpq option would otherwise let a
    correct-looking URL reach a different server.
    """
    raw = os.environ.get("DATABASE_URL")
    if raw is None or raw == "":
        _refuse(
            "DATABASE_URL must be set explicitly to the "
            f"{E2E_DATABASE_NAME} URL; refusing to guess a target."
        )
    try:
        url = make_url(raw)
    except Exception:  # any parse failure is the same refusal
        print("error: DATABASE_URL is not a valid database URL.", file=sys.stderr)
        raise SystemExit(2) from None
    if url.database != E2E_DATABASE_NAME:
        _refuse(
            f"refusing to touch database {url.database!r}: only "
            f"{E2E_DATABASE_NAME!r} may be reset or dropped by this script."
        )
    if url.drivername != E2E_SERVER_DRIVER:
        _refuse(f"refusing driver {url.drivername!r}: only {E2E_SERVER_DRIVER!r} is accepted.")
    if url.host != E2E_SERVER_HOST:
        _refuse(
            f"refusing host {url.host!r}: destructive E2E operations are "
            f"allowed only against {E2E_SERVER_HOST!r} (no remote hosts, no "
            "localhost aliases, no Unix sockets)."
        )
    if url.port != E2E_SERVER_PORT:
        _refuse(
            f"refusing port {url.port!r}: only the compose/CI server port "
            f"{E2E_SERVER_PORT} is accepted (and it must be explicit)."
        )
    if dict(url.query):
        _refuse(
            f"refusing URL query parameters {sorted(url.query)!r}: libpq "
            "options can override the connection target."
        )
    return url


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="reset_e2e_database",
        description=f"Recreate or drop the disposable {E2E_DATABASE_NAME} database.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--recreate",
        action="store_true",
        help="drop any stale copy, create fresh, and migrate to head",
    )
    mode.add_argument("--drop", action="store_true", help="drop the database")
    args = parser.parse_args(argv)

    url = _validated_url()
    admin_engine = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )

    def drop() -> None:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{E2E_DATABASE_NAME}" WITH (FORCE)'))

    try:
        drop()
        if args.drop:
            print(f"dropped {E2E_DATABASE_NAME}")
            return
        with admin_engine.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{E2E_DATABASE_NAME}"'))
        try:
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
            command.upgrade(config, "head")
        except BaseException:
            # Never leave a half-made database behind: the cleanup path
            # exists before creation begins and runs on any failure.
            drop()
            raise
        print(f"recreated {E2E_DATABASE_NAME} at the migration head")
    finally:
        admin_engine.dispose()


if __name__ == "__main__":
    main()
