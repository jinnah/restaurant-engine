"""Canonical OpenAPI export guarantees (ADR-009).

Three contracts: the export is deterministic; the committed artifact is
current (drift fails locally in plain ``uv run pytest``, before CI); and
the exported operation ids are exactly the declared, unique set.
"""

import json

from scripts.export_openapi import DEFAULT_OUTPUT, canonical_openapi_json

EXPECTED_OPERATION_IDS = {"health_live", "health_ready"}


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


def test_export_uses_lf_and_single_trailing_newline() -> None:
    text = canonical_openapi_json()
    assert "\r" not in text
    assert text.endswith("}\n")
    assert not text.endswith("\n\n")
