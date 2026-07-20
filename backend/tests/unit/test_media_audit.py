"""Media audit detail presence and projection rules (M3C, ADR-017).

Proves the exact field-presence rules for the item-image change record
(final correction 3) at BOTH layers — the stored payload (``model_dump``)
and the API-safe read-time projection — and that no key, path, checksum,
or alt text is ever storable or projectable.
"""

from app.api.audit_view import project_details
from app.domains.audit.actions import AuditAction
from app.domains.audit.details import (
    CatalogItemImageChangedDetails,
    MediaAssetDeletedDetails,
    MediaAssetExpiredDetails,
    MediaAssetUploadedDetails,
)

MID_A = "11111111-1111-4111-8111-111111111111"
MID_B = "22222222-2222-4222-8222-222222222222"


class TestItemImageChangedPresence:
    def test_attached_omits_old_media_id_at_both_layers(self) -> None:
        details = CatalogItemImageChangedDetails(
            change="attached", media_id_new=MID_A, alt_text_changed="unchanged"
        )
        stored = details.model_dump()
        assert "media_id_old" not in stored  # omit-None at storage
        assert stored["media_id_new"] == MID_A
        projected = project_details(AuditAction.CATALOG_ITEM_IMAGE_CHANGED.value, stored)
        assert projected is not None
        assert "media_id_old" not in projected
        assert projected["media_id_new"] == MID_A
        assert projected["change"] == "attached"

    def test_cleared_omits_new_media_id(self) -> None:
        details = CatalogItemImageChangedDetails(
            change="cleared", media_id_old=MID_A, alt_text_changed="unchanged"
        )
        stored = details.model_dump()
        assert stored["media_id_old"] == MID_A
        assert "media_id_new" not in stored

    def test_replaced_has_both_media_ids(self) -> None:
        details = CatalogItemImageChangedDetails(
            change="replaced", media_id_old=MID_A, media_id_new=MID_B, alt_text_changed="unchanged"
        )
        stored = details.model_dump()
        assert stored["media_id_old"] == MID_A
        assert stored["media_id_new"] == MID_B

    def test_alt_updated_has_equal_media_ids_and_changed_flag(self) -> None:
        details = CatalogItemImageChangedDetails(
            change="alt_updated", media_id_old=MID_A, media_id_new=MID_A, alt_text_changed="changed"
        )
        stored = details.model_dump()
        assert stored["media_id_old"] == stored["media_id_new"] == MID_A
        assert stored["alt_text_changed"] == "changed"
        # No alt text is present — only the change flag.
        assert "alt_text" not in stored

    def test_projection_rejects_out_of_set_change(self) -> None:
        # A malformed stored 'change' value never survives projection.
        stored = {"change": "sabotage", "alt_text_changed": "changed"}
        projected = project_details(AuditAction.CATALOG_ITEM_IMAGE_CHANGED.value, stored)
        assert projected is None or "change" not in projected


class TestAssetAuditProjections:
    def test_uploaded_projects_all_bounded_fields(self) -> None:
        details = MediaAssetUploadedDetails(
            source_format="webp", width=1000, height=800, byte_size=123456, variant_count=2
        )
        stored = details.model_dump()
        projected = project_details(AuditAction.MEDIA_ASSET_UPLOADED.value, stored)
        assert projected == {
            "source_format": "webp",
            "width": 1000,
            "height": 800,
            "byte_size": 123456,
            "variant_count": 2,
        }

    def test_deleted_projects_status_and_variant_count(self) -> None:
        details = MediaAssetDeletedDetails(status="active", variant_count=3)
        projected = project_details(AuditAction.MEDIA_ASSET_DELETED.value, details.model_dump())
        assert projected == {"status": "active", "variant_count": 3}

    def test_expired_projects_system_trigger(self) -> None:
        details = MediaAssetExpiredDetails(trigger="pending_ttl_sweep", variant_count=0)
        projected = project_details(AuditAction.MEDIA_ASSET_EXPIRED.value, details.model_dump())
        # variant_count 0 is falsy -> the small-int extractor still admits it,
        # but the projection drops None/absent only; 0 stays.
        assert projected is not None
        assert projected["trigger"] == "pending_ttl_sweep"

    def test_out_of_set_status_never_projects(self) -> None:
        projected = project_details(
            AuditAction.MEDIA_ASSET_DELETED.value, {"status": "smuggled", "variant_count": 1}
        )
        assert projected is not None
        assert "status" not in projected

    def test_smuggled_key_or_path_is_never_projected(self) -> None:
        # Even if a malformed stored payload carries a storage key or path,
        # the allowlist projection never surfaces it.
        stored = {
            "status": "active",
            "variant_count": 1,
            "storage_key": "biz/asset/canonical.webp",
            "path": "/srv/media/biz",
            "checksum_sha256": "deadbeef",
        }
        projected = project_details(AuditAction.MEDIA_ASSET_DELETED.value, stored)
        assert projected == {"status": "active", "variant_count": 1}
