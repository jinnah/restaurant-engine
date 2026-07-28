"""Storefront application service (M4B, ADR-020).

Owns every storefront transaction. Authorization is enforced here, in the
service (M2B discipline), against the three M4B capabilities: reads
require ``business.storefront.read``, draft mutations
``business.storefront.write``, publication and restoration
``business.storefront.publish`` (owner only). Broad ``business.view`` is
deliberately insufficient for any storefront read (§7).

Every mutation runs one preamble — capability, Business ``FOR UPDATE``
lock, lifecycle gate — so all storefront writes of one tenant serialize on
the Business row (§5.8) and closed businesses are immutable (§8) while
remaining readable. The draft is the single mutable working copy under
optimistic concurrency: every effective draft mutation increments
``lock_version`` and a stale write is a 409 carrying the current value,
never a silent overwrite (§6). Exact no-ops — a byte-identical canonical
config — write nothing, claim nothing, increment nothing, and record no
audit event (D-5; the M3 no-op-suppression precedent).

Media references follow the §10 ordering: validation precedes claiming,
and a rejected draft claims nothing. Unknown, cross-business, and
non-image references are one indistinguishable 422 (D-6) — existence is
not disclosed. An eligible pending asset is claimed through the same
``claim_for_attachment`` path the catalog uses, so an expired asset is
the established 409 ``invalid_state`` there.
"""

import copy
import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.orm import Session

from app.core.errors import (
    ApiError,
    ConflictError,
    ErrorCode,
    InvalidStateError,
    ResourceNotFoundError,
)
from app.domains.audit import recorder
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    StorefrontPublishedDetails,
    StorefrontVersionRestoredDetails,
)
from app.domains.identity.actor import ActorContext
from app.domains.identity.policies import Capability
from app.domains.media import repository as media_repository
from app.domains.media import service as media_service
from app.domains.storefront import repository, service_support, variants
from app.domains.storefront.composition import StorefrontConfig, dump_config, parse_config
from app.domains.storefront.models import StorefrontVersion, VersionState
from app.domains.storefront.schemas import (
    DraftPut,
    DraftView,
    PublishedSummary,
    PublishRequest,
    RestoreRequest,
    StorefrontOverview,
    VersionDetail,
    VersionPage,
    VersionSummary,
)
from app.domains.storefront.sections import referenced_media_ids
from app.domains.storefront.variants import DesignVariant


def _draft_view(row: StorefrontVersion) -> DraftView:
    """Project the draft row, fail-closed.

    A stored config or variant the code-owned registries no longer accept
    cannot arise through any application path (both registries are
    append-only and every write validated first), so a parse failure here
    is an integrity defect and propagates to the opaque internal-error
    boundary (approved completion 1) — never rendered as if valid.
    """
    return DraftView(
        config=parse_config(row.config),
        design_variant=DesignVariant(row.design_variant),
        lock_version=row.lock_version,
        schema_version=row.schema_version,
        source_version_id=row.source_version_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _published_summary(row: StorefrontVersion) -> PublishedSummary:
    # Non-draft rows always carry their publication pair and number (the
    # paired CHECKs); the asserts narrow the Optional columns for mypy.
    assert row.version_number is not None  # noqa: S101 - schema invariant
    assert row.published_at is not None  # noqa: S101 - schema invariant
    assert row.published_by_user_id is not None  # noqa: S101 - schema invariant
    return PublishedSummary(
        id=row.id,
        version_number=row.version_number,
        design_variant=DesignVariant(row.design_variant),
        schema_version=row.schema_version,
        published_at=row.published_at,
        published_by_user_id=row.published_by_user_id,
    )


# --- Reads -------------------------------------------------------------------


def get_overview(db: Session, actor: ActorContext, business_id: uuid.UUID) -> StorefrontOverview:
    """The storefront state: draft (or its valid absence) + published summary.

    Reads never create state (§5.1): a business with no draft reads as
    ``draft: null`` and the workspace shows a first-use state.
    """
    service_support.authorize_read(db, actor, business_id)
    draft = repository.get_draft(db, business_id=business_id)
    published = repository.get_published(db, business_id=business_id)
    return StorefrontOverview(
        draft=_draft_view(draft) if draft is not None else None,
        published=_published_summary(published) if published is not None else None,
    )


# --- Draft writing -----------------------------------------------------------


def _stale_draft_conflict(message: str, draft: StorefrontVersion) -> ApiError:
    """409 carrying the current lock version (§6) — never a silent overwrite."""
    return ApiError(
        409,
        ErrorCode.CONFLICT,
        message,
        details={"lock_version": draft.lock_version},
    )


def _claim_referenced_media(db: Session, business_id: uuid.UUID, config: StorefrontConfig) -> None:
    """Validate every media reference, then claim (§10, D-6).

    Validation precedes claiming and a failed validation leaves nothing
    claimed: unknown, cross-business, and non-image references raise one
    indistinguishable 422 before any promotion. Eligible references are
    then claimed through the same ``claim_for_attachment`` path the
    catalog item-image command uses — the whole sequence runs under the
    Business row lock the write preamble took, and media mutations take
    that same lock first, so an asset cannot vanish between validation and
    claim. An expired same-business pending asset is the established 409
    ``invalid_state`` from the claim path (final correction J).
    """
    ordered = list(
        dict.fromkeys(
            media_id for section in config.sections for media_id in referenced_media_ids(section)
        )
    )
    if not ordered:
        return
    unknown: list[str] = []
    for media_id in ordered:
        asset = media_repository.get_asset(db, business_id=business_id, asset_id=media_id)
        if asset is None or asset.kind != "image":
            unknown.append(str(media_id))
    if unknown:
        raise ApiError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "config references unknown media assets",
            details={"media_ids": unknown},
        )
    for media_id in ordered:
        media_service.claim_for_attachment(db, business_id, media_id)


def put_draft(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: DraftPut
) -> DraftView:
    """Create or replace the draft — full-document semantics (D-5).

    Create intent (``expected_lock_version`` omitted/null) inserts the
    first draft with the platform default variant and ``lock_version = 0``
    (§5.3); if a draft already exists the response is the established
    stale/conflict 409 and never an overwrite (§5.5). Update intent
    requires the exact current ``lock_version`` (§5.6). Owners and
    managers can never supply ``design_variant`` — the field is absent
    from their schema (§5.10).
    """
    service_support.authorize_write(db, actor, business_id, Capability.BUSINESS_STOREFRONT_WRITE)
    draft = repository.get_draft(db, business_id=business_id)

    if payload.expected_lock_version is None:
        if draft is not None:
            raise _stale_draft_conflict("a draft already exists for this business", draft)
        _claim_referenced_media(db, business_id, payload.config)
        row = StorefrontVersion(
            business_id=business_id,
            state=VersionState.DRAFT.value,
            version_number=None,
            schema_version=payload.config.schema_version,
            design_variant=variants.PLATFORM_DEFAULT_VARIANT.value,
            config=dump_config(payload.config),
            lock_version=0,
            source_version_id=None,
        )
        repository.add(db, row)
        service_support.safe_flush(db)
        service_support.safe_commit(db)
        return _draft_view(row)

    if draft is None:
        raise ConflictError("no draft exists to update; omit expected_lock_version to create one")
    if draft.lock_version != payload.expected_lock_version:
        raise _stale_draft_conflict("the draft has changed since it was read", draft)

    submitted = dump_config(payload.config)
    if draft.config == submitted:
        # Exact canonical no-op (D-5): no write, no lock increment, no
        # updated_at bump, no media claim, no audit. The view is built
        # before rollback so releasing the Business lock cannot expire it.
        view = _draft_view(draft)
        db.rollback()
        return view

    _claim_referenced_media(db, business_id, payload.config)
    draft.config = submitted
    draft.schema_version = payload.config.schema_version
    draft.lock_version += 1
    service_support.safe_flush(db)
    service_support.safe_commit(db)
    return _draft_view(draft)


# --- History reads -----------------------------------------------------------


def _version_summary(row: StorefrontVersion) -> VersionSummary:
    assert row.version_number is not None  # noqa: S101 - schema invariant
    assert row.published_at is not None  # noqa: S101 - schema invariant
    assert row.published_by_user_id is not None  # noqa: S101 - schema invariant
    return VersionSummary(
        id=row.id,
        version_number=row.version_number,
        state=cast(Literal["published", "archived"], row.state),
        design_variant=DesignVariant(row.design_variant),
        schema_version=row.schema_version,
        published_at=row.published_at,
        published_by_user_id=row.published_by_user_id,
        source_version_id=row.source_version_id,
        created_at=row.created_at,
    )


def list_versions(
    db: Session, actor: ActorContext, business_id: uuid.UUID, *, limit: int, offset: int
) -> VersionPage:
    """One owner-facing history page: published + archived, newest first."""
    service_support.authorize_read(db, actor, business_id)
    rows = repository.list_history(db, business_id=business_id, limit=limit, offset=offset)
    total = repository.count_history(db, business_id=business_id)
    return VersionPage(
        items=[_version_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_version_detail(
    db: Session, actor: ActorContext, business_id: uuid.UUID, version_id: uuid.UUID
) -> VersionDetail:
    """One history row with its composition.

    History rows only: the singleton draft is not part of this resource
    space, so requesting its id here is the same 404 as an unknown or
    cross-tenant id — the overview is the draft's only read surface.
    """
    service_support.authorize_read(db, actor, business_id)
    row = repository.get_version(db, business_id=business_id, version_id=version_id)
    if row is None or row.state == VersionState.DRAFT.value:
        raise ResourceNotFoundError("Version not found.")
    summary = _version_summary(row)
    return VersionDetail(**summary.model_dump(), config=parse_config(row.config))


# --- Publication -------------------------------------------------------------


def publish(
    db: Session, actor: ActorContext, business_id: uuid.UUID, payload: PublishRequest
) -> StorefrontOverview:
    """Publish the draft: promote, archive the predecessor, seed the next.

    One transaction under the Business row lock (§4). The version number is
    minted here and only here (max + 1). Statement order matters against
    the partial-unique singletons: the previous published row is archived
    (and flushed) before the draft is promoted, and the promotion is
    flushed before the seeded draft is inserted.
    """
    service_support.authorize_write(db, actor, business_id, Capability.BUSINESS_STOREFRONT_PUBLISH)
    draft = repository.get_draft(db, business_id=business_id)
    if draft is None:
        raise InvalidStateError("no draft exists to publish")
    if draft.lock_version != payload.expected_lock_version:
        raise _stale_draft_conflict("the draft has changed since it was read", draft)
    # Fail-closed re-validation before promotion (the publish-time half of
    # "invalid config cannot save"): a stored draft that no longer parses,
    # or carries an unregistered variant, is an integrity defect and
    # propagates to the opaque 500 — it is never published.
    config = parse_config(draft.config)
    variant = DesignVariant(draft.design_variant)
    number = repository.next_version_number(db, business_id=business_id)

    previous = repository.get_published(db, business_id=business_id)
    if previous is not None:
        previous.state = VersionState.ARCHIVED.value
        service_support.safe_flush(db)  # free the one-published slot first

    draft.state = VersionState.PUBLISHED.value
    draft.version_number = number
    draft.published_at = datetime.now(UTC)
    draft.published_by_user_id = actor.user.id
    service_support.safe_flush(db)  # free the one-draft slot before seeding

    seeded = StorefrontVersion(
        business_id=business_id,
        state=VersionState.DRAFT.value,
        version_number=None,
        schema_version=draft.schema_version,
        design_variant=draft.design_variant,
        config=copy.deepcopy(draft.config),
        lock_version=0,
        source_version_id=draft.id,
    )
    repository.add(db, seeded)
    service_support.safe_flush(db)
    recorder.record(
        db,
        AuditAction.STOREFRONT_PUBLISHED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="storefront_version",
        target_id=str(draft.id),
        details=StorefrontPublishedDetails(
            version_number=number,
            design_variant=variant.value,
            schema_version=draft.schema_version,
            section_count=len(config.sections),
        ),
    )
    service_support.safe_commit(db)
    return StorefrontOverview(
        draft=_draft_view(seeded),
        published=_published_summary(draft),
    )


# --- Restore -----------------------------------------------------------------


def restore_version(
    db: Session,
    actor: ActorContext,
    business_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: RestoreRequest,
) -> DraftView:
    """Overwrite the current draft from an archived version (§4, D-4).

    Archived sources only — restoring the current published row is
    deliberately unsupported under the approved archived-only ruling. The
    source is resolved tenant-scoped, so unknown and cross-tenant ids are
    the same 404; a same-business row in the wrong state is 409
    ``invalid_state``. Restore never publishes and never mutates the
    source. Every successful restore is an intentional, effective
    mutation (approved completion 2): repeated restores from the same
    source still increment ``lock_version``, refresh provenance, and emit
    a new audit event.
    """
    service_support.authorize_write(db, actor, business_id, Capability.BUSINESS_STOREFRONT_PUBLISH)
    source = repository.get_version(db, business_id=business_id, version_id=version_id)
    if source is None:
        raise ResourceNotFoundError("Version not found.")
    if source.state != VersionState.ARCHIVED.value:
        raise InvalidStateError("only archived versions can be restored")
    draft = repository.get_draft(db, business_id=business_id)
    if draft is None:
        raise InvalidStateError("no draft exists to restore into")
    if draft.lock_version != payload.expected_lock_version:
        raise _stale_draft_conflict("the draft has changed since it was read", draft)
    assert source.version_number is not None  # noqa: S101 - schema invariant
    # Fail-closed validation of the persisted source BEFORE any mutation
    # (approved completion 1): corrupt stored data propagates to the opaque
    # 500 and the draft — and the audit stream — stay untouched.
    parse_config(source.config)
    variant = DesignVariant(source.design_variant)

    draft.config = copy.deepcopy(source.config)
    draft.design_variant = source.design_variant
    draft.schema_version = source.schema_version
    draft.source_version_id = source.id
    draft.lock_version += 1
    service_support.safe_flush(db)
    recorder.record(
        db,
        AuditAction.STOREFRONT_VERSION_RESTORED,
        actor_user_id=actor.user.id,
        business_id=business_id,
        target_type="storefront_version",
        target_id=str(source.id),
        details=StorefrontVersionRestoredDetails(
            restored_from_version_number=source.version_number,
            design_variant=variant.value,
        ),
    )
    service_support.safe_commit(db)
    return _draft_view(draft)
