"""Media storage protocols and the local filesystem adapter (M3C).

The ruled interface (ADR-017 M3C record; blueprint §7.5 amendment):
runtime code sees ``MediaStorage`` (``put``/``open``/``delete``/``stat``);
operator tooling (the sweep, backup preflight) additionally sees
``MaintenanceStorage.iter_objects``. There is deliberately no
``public_url`` — application URLs are opaque asset ids plus logical
variant names, composed outside the adapter, and internal keys never
appear in API responses, audit details, logs, or URLs.

Keys are derived, never stored: ``{business_id}/{asset_id}/{variant}.webp``
— tenant-prefixed (docs/04) and randomized via the UUIDv4 asset id, with
no user-controlled component. The adapter validates every addressed key
against the strict shape and re-anchors the resolved path under the
root, so a malformed or traversal-shaped key is an error, not a file.
"""

import os
import re
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Protocol

from app.domains.media.policies import CANONICAL_VARIANT, VARIANT_NAMES

_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_VARIANTS = "|".join((CANONICAL_VARIANT, *VARIANT_NAMES))
KEY_RE = re.compile(
    f"^(?P<business_id>{_UUID})/(?P<asset_id>{_UUID})/(?P<variant>{_VARIANTS})\\.webp$"
)

# Temporary work area inside the root: upload scratch, readiness probes.
# Never contains addressable objects; stale entries fall under the sweep's
# temp-cleanup policy.
TMP_DIR_NAME = ".tmp"


class ObjectNotFoundError(Exception):
    """The addressed object does not exist in storage."""


@dataclass(frozen=True)
class StoredObjectStat:
    """Sweep-safe object metadata (final correction A)."""

    key: str  # internal; never leaves storage/sweep/verify code
    byte_size: int
    last_modified: datetime  # timezone-aware UTC


@dataclass(frozen=True)
class ParsedKey:
    business_id: uuid.UUID
    asset_id: uuid.UUID
    variant: str


def object_key(business_id: uuid.UUID, asset_id: uuid.UUID, variant: str) -> str:
    """Derive the internal storage key for one logical object."""
    if variant != CANONICAL_VARIANT and variant not in VARIANT_NAMES:
        msg = f"unknown logical variant: {variant!r}"
        raise ValueError(msg)
    return f"{business_id}/{asset_id}/{variant}.webp"


def parse_key(key: str) -> ParsedKey | None:
    """Parse a validly shaped key; ``None`` for malformed/unknown shapes."""
    match = KEY_RE.match(key)
    if match is None:
        return None
    return ParsedKey(
        business_id=uuid.UUID(match.group("business_id")),
        asset_id=uuid.UUID(match.group("asset_id")),
        variant=match.group("variant"),
    )


class MediaStorage(Protocol):
    """Runtime storage contract (ADR-017 M3C ruling)."""

    def put(self, *, key: str, content: BinaryIO, content_type: str) -> None: ...

    def open(self, *, key: str) -> BinaryIO: ...

    def delete(self, *, key: str) -> None: ...

    def stat(self, *, key: str) -> StoredObjectStat | None: ...


class MaintenanceStorage(MediaStorage, Protocol):
    """Runtime contract plus the operator-tooling inventory extension."""

    def iter_objects(self, *, prefix: str = "") -> Iterator[StoredObjectStat]: ...


class LocalFilesystemStorage:
    """Local persistent storage under ``MEDIA_STORAGE_ROOT`` (M3C adapter).

    Writes are atomic (temp file in ``.tmp`` on the same filesystem, then
    ``os.replace``); ``delete`` is idempotent and prunes empty asset/
    business directories best-effort. Every addressed key must match the
    strict key shape, and the resolved path is re-anchored under the
    root as defense in depth.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    def _tmp_dir(self) -> Path:
        tmp = self._root / TMP_DIR_NAME
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp

    def _path(self, key: str) -> Path:
        if KEY_RE.match(key) is None:
            msg = "invalid storage key shape"
            raise ValueError(msg)
        path = (self._root / Path(key)).resolve()
        if self._root.resolve() not in path.parents:
            msg = "storage key escapes the media root"  # pragma: no cover
            raise ValueError(msg)  # pragma: no cover - shape check already forbids
        return path

    def put(self, *, key: str, content: BinaryIO, content_type: str) -> None:
        # content_type is part of the protocol for provider adapters (an
        # S3 adapter sets it as object metadata); the filesystem needs
        # only the bytes.
        del content_type
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        scratch = self._tmp_dir() / f"put-{uuid.uuid4()}"
        try:
            with scratch.open("wb") as handle:
                shutil.copyfileobj(content, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(scratch, target)
        finally:
            scratch.unlink(missing_ok=True)

    def open(self, *, key: str) -> BinaryIO:
        try:
            return self._path(key).open("rb")
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    def delete(self, *, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        # Best-effort pruning of now-empty asset/business directories.
        for parent in (path.parent, path.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break

    def stat(self, *, key: str) -> StoredObjectStat | None:
        try:
            result = self._path(key).stat()
        except FileNotFoundError:
            return None
        return StoredObjectStat(
            key=key,
            byte_size=result.st_size,
            last_modified=datetime.fromtimestamp(result.st_mtime, tz=UTC),
        )

    def iter_objects(self, *, prefix: str = "") -> Iterator[StoredObjectStat]:
        """Every stored object (malformed keys included) except ``.tmp``.

        The sweep classifies shapes itself: malformed/unknown keys must be
        *visible* so they can be reported (never deleted) — filtering them
        here would hide exactly what the report exists to surface.
        """
        root = self._root
        if not root.exists():
            return
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name != TMP_DIR_NAME]
            for filename in filenames:
                path = Path(directory) / filename
                key = path.relative_to(root).as_posix()
                if prefix and not key.startswith(prefix):
                    continue
                result = path.stat()
                yield StoredObjectStat(
                    key=key,
                    byte_size=result.st_size,
                    last_modified=datetime.fromtimestamp(result.st_mtime, tz=UTC),
                )

    # --- Probes and maintenance (not part of the runtime protocol) --------

    def probe(self) -> None:
        """Write/stat/delete a collision-safe marker; raises ``OSError``.

        Used by the production startup check and the readiness endpoint.
        The marker lives in ``.tmp`` under a UUID name, so concurrent
        probes never race on one fixed filename and an abandoned marker
        falls under the stale-temp cleanup policy (final correction 7).
        """
        marker = self._tmp_dir() / f"probe-{uuid.uuid4()}"
        try:
            marker.write_bytes(b"probe")
            marker.stat()
        finally:
            marker.unlink(missing_ok=True)

    def startup_check(self) -> None:
        """Production fail-fast: the configured root must already exist.

        Development/test roots are created lazily; production must point
        at a durable, mounted directory — a missing root is a deployment
        error, never something to silently create inside an ephemeral
        container filesystem (final correction B).
        """
        if not self._root.is_dir():
            msg = (
                "MEDIA_STORAGE_ROOT does not exist or is not a directory; "
                "production requires an explicit durable media root"
            )
            raise RuntimeError(msg)
        self.probe()

    def cleanup_stale_temps(self, *, older_than_hours: int) -> int:
        """Delete ``.tmp`` entries older than the safety age; returns count."""
        tmp = self._root / TMP_DIR_NAME
        if not tmp.is_dir():
            return 0
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        removed = 0
        for path in tmp.iterdir():
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if modified <= cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed
