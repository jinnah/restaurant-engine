"""Canonical OpenAPI export guarantees (ADR-009).

Three contracts: the export is deterministic; the committed artifact is
current (drift fails locally in plain ``uv run pytest``, before CI); and
the exported operation ids are exactly the declared, unique set.
"""

import json

from scripts.export_openapi import DEFAULT_OUTPUT, canonical_openapi_json

EXPECTED_OPERATION_IDS = {
    "health_live",
    "health_ready",
    # M2A (ADR-010): authentication contract.
    "auth_login",
    "auth_logout",
    "auth_session",
    # M2B: tenancy and lifecycle (ADR-012: Business is the tenant aggregate).
    "platform_businesses_create",
    "platform_businesses_list",
    "platform_business_get",
    "platform_business_activate",
    "platform_business_suspend",
    "platform_business_reactivate",
    "platform_business_close",
    "business_get",
    # M2C (ADR-013): public host-resolved storefront surface.
    "public_site_get",
    # M2D (ADR-014): onboarding, recovery, entitlements, audit access.
    "business_invitation_create",
    "business_invitations_list",
    "business_invitation_revoke",
    "platform_invitation_create",
    "platform_invitations_list",
    "platform_invitation_revoke",
    "invitation_preview",
    "invitation_accept",
    "invitation_accept_existing",
    "platform_password_reset_issue",
    "password_reset_redeem",
    "platform_business_entitlements_set",
    "business_entitlements_get",
    "platform_audit_events_list",
    "business_audit_events_list",
    # M3A (ADR-017): catalog core administration.
    "catalog_admin_menu_get",
    "catalog_category_create",
    "catalog_category_update",
    "catalog_category_delete",
    "catalog_categories_reorder",
    "catalog_item_create",
    "catalog_item_get",
    "catalog_item_update",
    "catalog_item_delete",
    "catalog_items_reorder",
    "catalog_item_availability_set",
    "catalog_item_image_set",
    # M3B (ADR-017): modifier administration.
    "catalog_item_modifier_groups_get",
    "catalog_modifier_group_create",
    "catalog_modifier_group_update",
    "catalog_modifier_group_delete",
    "catalog_modifier_groups_reorder",
    "catalog_modifier_option_create",
    "catalog_modifier_option_update",
    "catalog_modifier_option_delete",
    "catalog_modifier_options_reorder",
    # M3C (ADR-017): media administration.
    "media_asset_upload",
    "media_assets_list",
    "media_asset_get",
    "media_asset_file_get",
    "media_asset_delete",
    # M3D (ADR-017): the host-resolved public surface.
    "public_menu_get",
    "public_media_file_get",
}


def test_export_is_deterministic() -> None:
    assert canonical_openapi_json() == canonical_openapi_json()


def test_committed_spec_is_current() -> None:
    assert DEFAULT_OUTPUT.exists(), (
        f"committed OpenAPI contract missing at {DEFAULT_OUTPUT}; "
        "run `corepack pnpm generate:client` from the repository root"
    )
    committed = DEFAULT_OUTPUT.read_bytes()
    fresh = canonical_openapi_json().encode("utf-8")
    assert committed == fresh, (
        "committed openapi.json is stale; run `corepack pnpm generate:client` "
        "from the repository root and commit both regenerated artifacts"
    )


def test_exported_operation_ids_are_expected_and_unique() -> None:
    document = json.loads(canonical_openapi_json())
    operation_ids = [
        operation["operationId"]
        for path_item in document["paths"].values()
        for operation in path_item.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert set(operation_ids) == EXPECTED_OPERATION_IDS
    # M3C brought the contract to 55; M3D adds the public menu and public
    # media delivery: the contract is exactly 57 operations. The two
    # schema-hidden HEAD companions add none (see below).
    assert len(EXPECTED_OPERATION_IDS) == 57


def test_public_media_documents_no_validation_error() -> None:
    """The public media route must not advertise a 422 (M3D correction C1).

    Its identifiers are hand-parsed so a malformed one is the neutral
    public 404, never a detailed validation envelope. FastAPI appends a 422
    to any operation with flat parameters, so the route declares none and
    publishes its parameter contract through ``openapi_extra`` instead —
    which must still document a uuid-formatted asset id and the closed
    variant set.
    """
    document = json.loads(canonical_openapi_json())
    operation = document["paths"]["/api/v1/public/media/{asset_id}/{variant}"]["get"]
    assert operation["operationId"] == "public_media_file_get"
    assert sorted(operation["responses"]) == ["200", "304", "404"]
    assert "422" not in operation["responses"]
    assert list(operation["responses"]["200"]["content"]) == ["image/webp"]
    assert operation["responses"]["404"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert parameters["asset_id"]["schema"] == {
        "type": "string",
        "format": "uuid",
        "title": "Asset Id",
    }
    assert parameters["variant"]["schema"]["enum"] == ["canonical", "w320", "w640", "w1280"]
    assert all(parameter["in"] == "path" for parameter in operation["parameters"])
    assert all(parameter["required"] for parameter in operation["parameters"])


def test_parameterized_administrative_contracts_are_unchanged() -> None:
    """The 422 suppression is route-local (M3D correction C1).

    Administrative endpoints keep FastAPI's automatic validation-error
    response, so nothing global was altered to remove it from one public
    route. The admin media preview is the closest analogue — same shape,
    same domain — and must still document its 422.
    """
    document = json.loads(canonical_openapi_json())
    admin_preview = document["paths"][
        "/api/v1/businesses/{business_id}/media/{asset_id}/file/{variant}"
    ]["get"]
    assert sorted(admin_preview["responses"]) == ["200", "401", "404", "422"]

    parameterized = [
        operation["operationId"]
        for item in document["paths"].values()
        for operation in item.values()
        if operation.get("parameters") or operation.get("requestBody")
    ]
    with_422 = {
        operation["operationId"]
        for item in document["paths"].values()
        for operation in item.values()
        if "422" in operation["responses"]
    }
    # Every parameterized operation except the one deliberately suppressed
    # still documents a 422.
    missing = [op for op in parameterized if op not in with_422]
    assert missing == ["public_media_file_get"]


def test_head_companions_add_no_operation() -> None:
    """Schema-hidden HEAD routes must not enter the contract (M3D, R11).

    ``HEAD`` is served by a companion route on the same handler; declaring
    it as a method instead would emit a second operation reusing the GET's
    operation id, inflating the count and breaking the generated client.
    """
    document = json.loads(canonical_openapi_json())
    assert not [path for path, item in document["paths"].items() if "head" in item]


def test_media_upload_multipart_request_body_is_pinned() -> None:
    """The upload declares no body param; its multipart contract is supplied
    manually via ``openapi_extra`` (ADR-009 + the binding upload ruling), so
    the exported requestBody must stay exactly this single-file schema."""
    document = json.loads(canonical_openapi_json())
    operations = [
        operation
        for path_item in document["paths"].values()
        for operation in path_item.values()
        if operation.get("operationId") == "media_asset_upload"
    ]
    assert len(operations) == 1
    request_body = operations[0]["requestBody"]
    assert request_body["required"] is True
    content = request_body["content"]
    # Exactly one media type: multipart/form-data.
    assert list(content.keys()) == ["multipart/form-data"]
    schema = content["multipart/form-data"]["schema"]
    assert schema["type"] == "object"
    assert schema["required"] == ["file"]
    # Exactly ONE property — the single binary file — and no other form
    # fields are advertised (the pin is exact).
    assert list(schema["properties"].keys()) == ["file"]
    assert schema["properties"]["file"] == {
        "type": "string",
        "format": "binary",
        "description": "A single static JPEG, PNG, or WebP image.",
    }
    # additionalProperties must be present and exactly False — no omission
    # permitted (no ``.get`` fallback).
    assert schema["additionalProperties"] is False


def test_price_bound_is_advertised_in_the_contract() -> None:
    # F1 ruling (ADR-017): the public contract advertises the approved
    # price range on both the create and update schemas.
    document = json.loads(canonical_openapi_json())
    schemas = document["components"]["schemas"]
    for schema_name in ("ItemCreate", "ItemUpdate"):
        price = schemas[schema_name]["properties"]["price_minor"]
        variants = price.get("anyOf", [price])  # ItemUpdate's field is nullable
        integer_variant = next(part for part in variants if part.get("type") == "integer")
        assert integer_variant["maximum"] == 10_000_000
        assert integer_variant["minimum"] == 0


def test_export_uses_lf_and_single_trailing_newline() -> None:
    text = canonical_openapi_json()
    assert "\r" not in text
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")
