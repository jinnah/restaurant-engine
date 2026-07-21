"""Media application service (M3C, ADR-017).

Owns every media transaction. Reads (list/get/preview) authorize with
``business.view`` (staff included); mutations (upload/delete) require
``business.media.write`` (owner/manager). The item-image attachment
command lives in the catalog service and calls ``claim_for_attachment``
here inside its own transaction (the acyclic graph: catalog → media,
never the reverse — final correction M).

The upload worker (``process_and_store``) runs entirely inside an AnyIO
worker thread: it opens, uses, and closes its OWN session (no session,
ORM object, or transaction crosses the thread boundary — final
correction 2), writes every processed object to storage tracking each
key, then commits one short authoritative transaction (Business
``FOR UPDATE`` lock → quota check → insert → audit). Any failure after
the first object write triggers compensation — every tracked key is
deleted — and never masks the original error (final corrections G/N).
"""

import uuid
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    ApiError,
    ErrorCode,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import MediaAssetDeletedDetails, MediaAssetUploadedDetails
from app.domains.identity.actor import ActorContext
from app.domains.media import policies, repository
from app.domains.media.models import MediaAsset, MediaAssetVariant
from app.domains.media.processing import ImageValidationError, ProcessedImage, process_image
from app.domains.media.schemas import MediaAssetPage, MediaAssetView, MediaVariantView
from app.domains.media.service_support import (
    authorize_read,
    authorize_write_locking,
    authorize_write_locking_by_user_id,
    safe_commit,
    safe_flush,
)
from app.domains.media.storage import MediaStorage, ObjectNotFoundError, object_key
from app.domains.media.upload import extract_single_file


class AttachmentClaim:
    """The result of claiming a media asset for a catalog attachment."""

    def __init__(self, asset_id: uuid.UUID, promoted: bool) -> None:
        self.asset_id = asset_id
        self.promoted = promoted


def _quota_conflict(message: str, limit: int) -> ApiError:
    return ApiError(409, ErrorCode.CONFLICT, message, details={"limit": limit})


def _variant_views(variants: list[MediaAssetVariant]) -> list[MediaVariantView]:
    return [
        MediaVariantView(
            variant=variant.variant,  # type: ignore[arg-type]
            width=variant.width,
            height=variant.height,
            byte_size=variant.byte_size,
        )
        for variant in variants
    ]


def _asset_view(asset: MediaAsset, variants: list[MediaAssetVariant]) -> MediaAssetView:
    return MediaAssetView(
        id=asset.id,
        kind=asset.kind,  # type: ignore[arg-type]
        status=asset.status,  # type: ignore[arg-type]
        pending_expires_at=asset.pending_expires_at,
        original_filename=asset.original_filename,
        source_format=asset.source_format,  # type: ignore[arg-type]
        width=asset.width,
        height=asset.height,
        byte_size=asset.byte_size,
        variants=_variant_views(variants),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


# --- Reads --------------------------------------------------------------------


def list_assets(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> MediaAssetPage:
    """A page of the business's assets, newest first (any member)."""
    authorize_read(db, actor, business_id)
    assets = repository.list_assets(
        db, business_id=business_id, limit=limit, offset=offset, status=status
    )
    variants_by_asset = repository.list_variants_for_assets(
        db, business_id=business_id, asset_ids=[asset.id for asset in assets]
    )
    total = repository.count_assets(db, business_id=business_id, status=status)
    return MediaAssetPage(
        items=[_asset_view(asset, variants_by_asset.get(asset.id, [])) for asset in assets],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_asset(
    db: Session, actor: ActorContext, business_id: uuid.UUID, asset_id: uuid.UUID
) -> MediaAssetView:
    """One asset with its variants (any member; pending included)."""
    authorize_read(db, actor, business_id)
    asset = repository.get_asset(db, business_id=business_id, asset_id=asset_id)
    if asset is None:
        raise ResourceNotFoundError("Media asset not found.")
    variants = repository.list_variants(db, business_id=business_id, asset_id=asset_id)
    return _asset_view(asset, variants)


def open_asset_object(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    variant: str,
    storage: MediaStorage,
) -> BinaryIO:
    """Open one asset object for authorized admin preview (pending allowed).

    Returns a binary stream of the stored WebP. A missing canonical or a
    missing/unknown variant is a neutral 404 (final correction N) — the
    row can exist while its object does not.
    """
    authorize_read(db, actor, business_id)
    asset = repository.get_asset(db, business_id=business_id, asset_id=asset_id)
    if asset is None:
        raise ResourceNotFoundError("Media asset not found.")
    if variant != policies.CANONICAL_VARIANT:
        known = {
            item.variant
            for item in repository.list_variants(db, business_id=business_id, asset_id=asset_id)
        }
        if variant not in known:
            raise ResourceNotFoundError("Media variant not found.")
    try:
        return storage.open(key=object_key(business_id, asset_id, variant))
    except (ObjectNotFoundError, ValueError) as exc:
        raise ResourceNotFoundError("Media object not found.") from exc


# --- Delete -------------------------------------------------------------------


def delete_asset(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    asset_id: uuid.UUID,
    storage: MediaStorage,
) -> None:
    """Hard-delete an asset (row + variants CASCADE + audit), then objects.

    A referenced asset is protected by the ``menu_items`` RESTRICT FK,
    converted to a 409 by ``safe_flush``. Objects are deleted only after
    the database commit; a failed object delete leaves a sweep-visible
    orphan (never the reverse — the row never outlives its objects here
    because the row is gone first).
    """
    authorize_write_locking(db, actor, business_id)
    asset = repository.lock_asset(db, business_id=business_id, asset_id=asset_id)
    if asset is None:
        raise ResourceNotFoundError("Media asset not found.")
    status = asset.status
    variants = repository.list_variants(db, business_id=business_id, asset_id=asset_id)
    keys = [object_key(business_id, asset_id, policies.CANONICAL_VARIANT)]
    keys += [object_key(business_id, asset_id, variant.variant) for variant in variants]
    repository.delete_asset(db, asset)
    safe_flush(db)  # RESTRICT violation (referenced) -> 409 here
    recorder.record(
        db,
        AuditAction.MEDIA_ASSET_DELETED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="media_asset",
        target_id=str(asset_id),
        details=MediaAssetDeletedDetails(
            status=status,  # type: ignore[arg-type]
            variant_count=len(variants),
        ),
    )
    safe_commit(db)
    # Best-effort object deletion after the row is durably gone.
    for key in keys:
        storage.delete(key=key)


# --- Attachment (called by the catalog service, within its transaction) -------


def claim_for_attachment(
    db: Session, business_id: uuid.UUID, media_id: uuid.UUID
) -> AttachmentClaim:
    """Validate + promote an asset for a catalog attachment (M3C).

    Called by the catalog item-image command inside the catalog
    transaction, which already holds the Business ``FOR UPDATE`` lock, so
    the attach-vs-delete race is serialized on that shared lock. Validates
    same-business existence and ``kind='image'``, and requires an unexpired
    status on the database clock; an expired-pending asset returns 409
    ``invalid_state`` (final correction J). Promotes ``pending → active``
    (one-way); an already-active asset is a no-op promotion.
    """
    asset = repository.lock_asset(db, business_id=business_id, asset_id=media_id)
    if asset is None or asset.kind != "image":
        raise ResourceNotFoundError("Media asset not found.")
    if asset.status == "pending":
        # Decide expiry on the DATABASE clock while holding the lock: at
        # exact equality the asset is expired (final correction J).
        still_valid = db.execute(
            select(MediaAsset.pending_expires_at > func.now()).where(
                MediaAsset.business_id == business_id, MediaAsset.id == media_id
            )
        ).scalar_one()
        if not still_valid:
            raise InvalidStateError("this media asset has expired and cannot be attached")
        asset.status = "active"
        asset.pending_expires_at = None
        safe_flush(db)
        return AttachmentClaim(asset_id=media_id, promoted=True)
    return AttachmentClaim(asset_id=media_id, promoted=False)


# --- Upload (worker-thread transaction; final corrections 1/2/G/N) ------------


def process_upload(
    *,
    session_factory: sessionmaker[Session],
    storage: MediaStorage,
    business_id: uuid.UUID,
    actor: ActorContext,
    content_type_header: str,
    body: SpooledTemporaryFile[bytes],
    file_max_bytes: int,
    scratch_dir: Path,
) -> MediaAssetView:
    """The complete upload worker — runs entirely in an AnyIO worker thread.

    Multipart extraction, scratch-file creation, Pillow processing, object
    storage, and the authoritative transaction all run here off the event
    loop (final correction 2); only the bounded async body streaming that
    produced ``body`` ran on the loop. The extracted part's temp file is
    always removed.
    """
    scratch_dir.mkdir(parents=True, exist_ok=True)
    extracted = extract_single_file(
        content_type_header, body, file_max_bytes=file_max_bytes, work_dir=scratch_dir
    )
    try:
        return _process_and_store(
            session_factory=session_factory,
            storage=storage,
            business_id=business_id,
            actor=actor,
            spooled_path=extracted.path,
            original_filename=policies.sanitize_filename(extracted.filename),
            declared_content_type=extracted.content_type,
            scratch_dir=scratch_dir,
        )
    finally:
        extracted.path.unlink(missing_ok=True)


def _process_and_store(
    *,
    session_factory: sessionmaker[Session],
    storage: MediaStorage,
    business_id: uuid.UUID,
    actor: ActorContext,
    spooled_path: Path,
    original_filename: str,
    declared_content_type: str,
    scratch_dir: Path,
) -> MediaAssetView:
    """Process one upload and persist it (final correction 1).

    All fallible database work — the quota check, insert, audit, and the
    full response projection — happens **before** commit; a successful
    commit is the last database operation. A failure that definitely
    occurs before commit compensates every written object. Once the commit
    has been attempted, the outcome is treated as ambiguous: objects are
    deleted only if a separate transaction positively proves the asset row
    is absent; otherwise they are retained for reconciliation (the
    row-to-object invariant always wins over eager orphan cleanup).
    """
    asset_id = uuid.uuid4()
    written_keys: list[str] = []
    processed: ProcessedImage | None = None
    commit_attempted = False
    try:
        try:
            with spooled_path.open("rb") as source:
                processed = process_image(source, scratch_dir)
        except ImageValidationError as exc:
            # A rejected image is a client validation error (422), not a 500.
            raise ApiError(422, ErrorCode.VALIDATION_ERROR, str(exc)) from exc

        # Write canonical + variants; record each key as it succeeds so
        # compensation can remove exactly what exists.
        canonical_key = object_key(business_id, asset_id, policies.CANONICAL_VARIANT)
        with processed.canonical.path.open("rb") as handle:
            storage.put(key=canonical_key, content=handle, content_type="image/webp")
        written_keys.append(canonical_key)
        for variant in processed.variants:
            key = object_key(business_id, asset_id, variant.variant)
            with variant.path.open("rb") as handle:
                storage.put(key=key, content=handle, content_type="image/webp")
            written_keys.append(key)

        with session_factory() as db:
            # Every fallible database read/write AND the response projection
            # are built here, before commit.
            view = _prepare_uploaded_asset(
                db,
                business_id=business_id,
                actor=actor,
                asset_id=asset_id,
                processed=processed,
                original_filename=original_filename,
                declared_content_type=declared_content_type,
            )
            commit_attempted = True
            safe_commit(db)  # the FINAL database operation
        return view
    except BaseException:
        if commit_attempted:
            # Outcome-ambiguous: the commit may or may not have persisted the
            # row. Delete objects ONLY if a fresh transaction positively
            # proves the row is absent; otherwise retain them (a committed
            # row must never lose its objects — final correction 1).
            if _asset_row_absent(session_factory, business_id, asset_id):
                _compensate(storage, written_keys)
        else:
            # Definitely before commit: no row can exist, so compensate.
            _compensate(storage, written_keys)
        raise
    finally:
        if processed is not None:
            processed.canonical.path.unlink(missing_ok=True)
            for variant in processed.variants:
                variant.path.unlink(missing_ok=True)


def _prepare_uploaded_asset(
    db: Session,
    *,
    business_id: uuid.UUID,
    actor: ActorContext,
    asset_id: uuid.UUID,
    processed: ProcessedImage,
    original_filename: str,
    declared_content_type: str,
) -> MediaAssetView:
    """All pre-commit database work + the response projection (correction 1).

    Runs the authoritative preamble (capability + Business ``FOR UPDATE`` +
    lifecycle), the quota check, the insert, the audit event, and then
    loads and projects the stored asset — all inside the open transaction,
    before the caller commits. The returned view therefore needs no further
    database access after commit.
    """
    authorize_write_locking_by_user_id(db, actor.user.id, business_id)

    usage = repository.business_usage(db, business_id=business_id)
    candidate_bytes = processed.total_bytes
    if usage.asset_count + 1 > policies.MAX_MEDIA_ASSETS_PER_BUSINESS:
        raise _quota_conflict(
            "Media asset limit reached for this business.",
            policies.MAX_MEDIA_ASSETS_PER_BUSINESS,
        )
    if usage.stored_bytes + candidate_bytes > policies.MAX_MEDIA_BYTES_PER_BUSINESS:
        raise _quota_conflict(
            "Media storage limit reached for this business.",
            policies.MAX_MEDIA_BYTES_PER_BUSINESS,
        )

    asset = MediaAsset(
        id=asset_id,
        business_id=business_id,
        kind="image",
        status="pending",
        original_filename=original_filename,
        declared_content_type=declared_content_type[: policies.MAX_ORIGINAL_FILENAME_LENGTH],
        source_format=processed.source_format,
        width=processed.canonical.width,
        height=processed.canonical.height,
        byte_size=processed.canonical.byte_size,
        checksum_sha256=processed.canonical.checksum_sha256,
    )
    # pending_expires_at is set on the database clock (now() + 48h).
    asset.pending_expires_at = func.now() + func.make_interval(
        0, 0, 0, 0, policies.PENDING_TTL_HOURS
    )
    repository.add(db, asset)
    for variant in processed.variants:
        repository.add(
            db,
            MediaAssetVariant(
                business_id=business_id,
                asset_id=asset_id,
                variant=variant.variant,
                width=variant.width,
                height=variant.height,
                byte_size=variant.byte_size,
                checksum_sha256=variant.checksum_sha256,
            ),
        )
    safe_flush(db)
    recorder.record(
        db,
        AuditAction.MEDIA_ASSET_UPLOADED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="media_asset",
        target_id=str(asset_id),
        details=MediaAssetUploadedDetails(
            source_format=processed.source_format,  # type: ignore[arg-type]
            width=processed.canonical.width,
            height=processed.canonical.height,
            byte_size=processed.canonical.byte_size,
            variant_count=len(processed.variants),
        ),
    )
    # Load the server-assigned values (timestamps, pending_expires_at) and
    # project the response NOW — the last fallible work before commit.
    db.refresh(asset)
    variants = repository.list_variants(db, business_id=business_id, asset_id=asset_id)
    return _asset_view(asset, variants)


def _asset_row_absent(
    session_factory: sessionmaker[Session], business_id: uuid.UUID, asset_id: uuid.UUID
) -> bool:
    """Prove, in a fresh transaction, that the asset row does not exist.

    Returns ``True`` only on a positive absence proof. If the probe itself
    fails (the database is unreachable, etc.), absence cannot be proved, so
    it returns ``False`` and the caller retains the objects (correction 1).
    """
    try:
        with session_factory() as db:
            found = db.execute(
                select(MediaAsset.id).where(
                    MediaAsset.business_id == business_id, MediaAsset.id == asset_id
                )
            ).scalar_one_or_none()
        return found is None
    except Exception:
        return False


def _compensate(storage: MediaStorage, written_keys: list[str]) -> None:
    """Best-effort deletion of every written object (correction 1/N).

    Failures are swallowed — a failed compensation leaves a sweep-visible
    orphan and must never mask the original error.
    """
    for key in written_keys:
        try:
            storage.delete(key=key)
        except Exception:  # noqa: S110 - orphan-on-failure is acceptable (swept later)
            pass
