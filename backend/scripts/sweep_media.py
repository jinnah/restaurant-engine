"""Media storage sweep — operator maintenance CLI (M3C, ADR-017).

Dry run by default; ``--apply`` performs deletions; ``--verify`` runs the
coordinated-backup preflight (docs/07) — enumerating every expected object,
comparing byte size and a recomputed SHA-256 against the database, and
flagging every storage-only object regardless of age. Verify never mutates.

Usage (from the repository root)::

    uv run --directory backend python -m scripts.sweep_media            # dry run
    uv run --directory backend python -m scripts.sweep_media --apply
    uv run --directory backend python -m scripts.sweep_media --verify

Exit codes (operator contract):

* ``0`` — success: no failures and no outstanding work.
* ``1`` — a failure occurred: a ``--verify`` inconsistency, or an object
  deletion failed during ``--apply`` (orphans remain; investigate).
* ``2`` — invalid arguments (e.g. a non-positive ``--batch-size``).
* ``3`` — work remains: unresolved operator work that this run did not (or
  could not) clear. In either mode this includes asset rows whose objects
  are missing and malformed/unknown storage entries (never auto-deleted);
  in a dry run it additionally includes expired-pending assets, deletable
  orphans, and stale temps that ``--apply`` would remove.

The database comes from validated settings (``DATABASE_URL`` / ``.env``)
and the media root from ``MEDIA_STORAGE_ROOT`` — exactly like the API
process. Output carries business ids, asset ids, logical variants, and
counts only; internal storage keys and filesystem paths are never printed.
"""

import argparse
import sys

from app.core.database import create_database_engine, create_session_factory
from app.core.settings import load_settings

# Standalone scripts must load the COMPLETE model registry (see
# create_platform_admin.py): media rows reference businesses.id.
from app.domains.businesses import models as _businesses_models  # noqa: F401
from app.domains.catalog import models as _catalog_models  # noqa: F401
from app.domains.identity import models as _identity_models  # noqa: F401
from app.domains.media import models as _media_models  # noqa: F401
from app.domains.media import sweep
from app.domains.media.storage import LocalFilesystemStorage
from app.domains.media.sweep import SweepReport, VerifyReport

_MAX_BATCH_SIZE = 100_000


def _batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch-size must be an integer") from exc
    if parsed < 1 or parsed > _MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(f"batch-size must be between 1 and {_MAX_BATCH_SIZE}")
    return parsed


def _print_report(report: SweepReport) -> None:
    mode = "APPLY" if report.apply else "DRY RUN"
    print(f"media sweep ({mode}):")
    print(
        f"  expired-pending {'deleted' if report.apply else 'eligible'}: "
        f"{report.expired_pending_deleted}"
    )
    print(f"  expired object failures:   {report.expired_object_delete_failures}")
    print(
        f"  orphan objects {'deleted' if report.apply else 'eligible'}:  {report.orphans_deleted}"
    )
    print(f"  orphan objects too young:  {report.orphans_too_young}")
    print(f"  orphan delete failures:    {report.orphan_delete_failures}")
    print(f"  malformed keys (report):   {report.malformed_keys}")
    print(
        f"  stale temp files {'deleted' if report.apply else 'eligible'}: "
        f"{report.stale_temps_deleted}"
    )
    print(f"  rows missing objects:      {len(report.missing_objects)}")
    for missing in report.missing_objects:
        print(
            f"    - business {missing.business_id} asset {missing.asset_id}"
            f" variant {missing.variant}"
        )


def _print_verify(report: VerifyReport) -> None:
    print("media backup verify:")
    print(f"  findings:        {len(report.findings)}")
    print(f"  malformed keys:  {report.malformed_keys}")
    for finding in report.findings:
        print(
            f"    - {finding.kind}: business {finding.business_id}"
            f" asset {finding.asset_id} variant {finding.variant}"
        )


def _sweep_exit_code(report: SweepReport) -> int:
    failures = report.expired_object_delete_failures + report.orphan_delete_failures
    if failures:
        return 1
    # Malformed/unknown storage entries are never auto-deleted, so they are
    # unresolved operator work in BOTH modes (round-2 finding 4).
    work_remains = len(report.missing_objects) > 0 or report.malformed_keys > 0
    if not report.apply:
        work_remains = work_remains or bool(
            report.expired_pending_deleted or report.orphans_deleted or report.stale_temps_deleted
        )
    return 3 if work_remains else 0


def _verify_exit_code(report: VerifyReport) -> int:
    """0 when the backup set is consistent, else 1 (round-2 finding 3)."""
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Media storage sweep (M3C).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="perform deletions")
    group.add_argument(
        "--verify",
        action="store_true",
        help="backup preflight: require zero inconsistencies and zero orphans",
    )
    parser.add_argument("--batch-size", type=_batch_size, default=200)
    args = parser.parse_args(argv)

    settings = load_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    storage = LocalFilesystemStorage(settings.media_storage_root_path)

    try:
        if args.verify:
            verify = sweep.verify_backup(session_factory, storage, batch_size=args.batch_size)
            _print_verify(verify)
            code = _verify_exit_code(verify)
            if code == 0:
                print("verify OK: database and media root are a consistent set")
            else:
                print(
                    "verify FAILED: the database and media root are not a consistent set",
                    file=sys.stderr,
                )
            return code

        report = sweep.run_sweep(
            session_factory, storage, apply=args.apply, batch_size=args.batch_size
        )
    finally:
        engine.dispose()

    _print_report(report)
    return _sweep_exit_code(report)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
