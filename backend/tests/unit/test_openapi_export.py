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
