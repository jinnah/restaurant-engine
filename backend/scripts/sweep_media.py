"""Media storage sweep — operator maintenance CLI (M3C, ADR-017).

Dry run by default; ``--apply`` performs deletions. Also provides a
``--verify`` mode for the coordinated-backup preflight (docs/07): a
consistent database + media set reports zero rows-without-objects and
zero storage-only orphans.

Usage (from the repository root)::

    uv run --directory backend python -m scripts.sweep_media            # dry run
    uv run --directory backend python -m scripts.sweep_media --apply
    uv run --directory backend python -m scripts.sweep_media --verify

The database comes from validated settings (``DATABASE_URL`` / ``.env``)
and the media root from ``MEDIA_STORAGE_ROOT`` — exactly like the API
process. Output carries business ids, asset ids, logical variants, and
counts only; internal storage keys and filesystem paths are never
printed.
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
from app.domains.media.sweep import SweepReport


def _print_report(report: SweepReport) -> None:
    mode = "APPLY" if report.apply else "DRY RUN"
    print(f"media sweep ({mode}):")
    print(f"  expired-pending deleted:   {report.expired_pending_deleted}")
    print(f"  expired object failures:   {report.expired_object_delete_failures}")
    print(f"  orphan objects deleted:    {report.orphans_deleted}")
    print(f"  orphan objects too young:  {report.orphans_too_young}")
    print(f"  orphan delete failures:    {report.orphan_delete_failures}")
    print(f"  malformed keys (report):   {report.malformed_keys}")
    print(f"  stale temp files deleted:  {report.stale_temps_deleted}")
    print(f"  rows missing objects:      {len(report.missing_objects)}")
    for missing in report.missing_objects:
        print(
            f"    - business {missing.business_id} asset {missing.asset_id}"
            f" variant {missing.variant}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Media storage sweep (M3C).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="perform deletions")
    group.add_argument(
        "--verify",
        action="store_true",
        help="backup preflight: require zero missing objects and zero orphans",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args(argv)

    settings = load_settings()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    storage = LocalFilesystemStorage(settings.media_storage_root_path)

    try:
        # Verify never deletes; it reports the two consistency conditions.
        report = sweep.run_sweep(
            session_factory,
            storage,
            apply=False if args.verify else args.apply,
            batch_size=args.batch_size,
        )
    finally:
        engine.dispose()

    _print_report(report)

    if args.verify:
        # A consistent backup set has no rows-without-objects and no
        # storage-only orphans (the sweep's dry-run "would-delete" count).
        problems = len(report.missing_objects) + report.orphans_deleted
        if problems:
            print(
                "verify FAILED: the database and media root are not a consistent set",
                file=sys.stderr,
            )
            return 1
        print("verify OK: database and media root are consistent")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
