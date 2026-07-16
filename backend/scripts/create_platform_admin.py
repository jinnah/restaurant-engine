"""Create a platform administrator account (M2A bootstrap, ADR-010).

The only way accounts come into existence in Milestone 2A: development
setup and, later, first-production bootstrap (Milestone 8 runbook). No
seed credentials exist anywhere in the repository.

Usage (from the repository root)::

    uv run --directory backend python -m scripts.create_platform_admin \
        --email admin@example.com --display-name "Platform Admin"

The password is requested interactively without echo. For automation,
``--password-stdin`` reads it from standard input instead. A ``--password``
argument deliberately does not exist: argv leaks into shell history and
process listings.

The database comes from validated settings (``DATABASE_URL`` / ``.env``),
exactly like the API process.
"""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from app.core.database import create_database_engine
from app.core.settings import load_settings
from app.domains.identity.service import create_platform_admin


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("Password (input hidden): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("error: passwords do not match", file=sys.stderr)
        raise SystemExit(1)
    return first


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="create_platform_admin",
        description="Create a platform administrator (audited; fails on duplicates).",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from standard input instead of prompting",
    )
    args = parser.parse_args(argv)

    password = _read_password(args.password_stdin)

    engine = create_database_engine(load_settings())
    try:
        with Session(engine) as db:
            user = create_platform_admin(
                db,
                email=args.email,
                display_name=args.display_name,
                password=password,
            )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        engine.dispose()

    print(f"created platform admin {user.email} ({user.id})")


if __name__ == "__main__":
    main()
