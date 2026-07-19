"""Create, migrate, or drop the disposable E2E database (M2F, ADR-016).

The ONLY database this script will ever touch is ``restaurant_engine_e2e``.
The name is validated against that exact literal BEFORE any connection is
opened or any SQL runs: the development database (``restaurant_engine``),
the standing test database (``restaurant_engine_test``), and anything
unexpected are hard refusals. The E2E orchestrator constructs the target
URL itself — an inherited or hand-typed ``DATABASE_URL`` naming any other
database cannot get past the allowlist.

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

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

E2E_DATABASE_NAME = "restaurant_engine_e2e"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _validated_url() -> URL:
    """The target URL, hard-refused unless it names the E2E database."""
    raw = os.environ.get("DATABASE_URL")
    if raw is None or raw == "":
        print(
            "error: DATABASE_URL must be set explicitly to the "
            f"{E2E_DATABASE_NAME} URL; refusing to guess a target.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        url = make_url(raw)
    except Exception:  # any parse failure is the same refusal
        print("error: DATABASE_URL is not a valid database URL.", file=sys.stderr)
        raise SystemExit(2) from None
    if url.database != E2E_DATABASE_NAME:
        print(
            f"error: refusing to touch database {url.database!r}: only "
            f"{E2E_DATABASE_NAME!r} may be reset or dropped by this script.",
            file=sys.stderr,
        )
        raise SystemExit(2)
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
