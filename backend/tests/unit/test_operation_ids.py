"""Operation-ID contract enforcement (ADR-009).

Operation IDs feed the generated TypeScript client, so every schema-visible
route must declare one explicitly and they must be unique. The validator
runs inside ``create_app``; these tests prove both failure modes and that
the composed application passes.
"""

import pytest
from fastapi import FastAPI

from app.core.openapi import assert_contract_operation_ids
from app.main import create_app
from tests.conftest import make_settings


def test_composed_application_passes_validation() -> None:
    # create_app already calls the validator; constructing without an
    # exception is the contract. Re-running it directly must also pass.
    app = create_app(make_settings())
    assert_contract_operation_ids(app)


def test_route_without_explicit_operation_id_is_rejected() -> None:
    app = FastAPI()

    @app.get("/things")
    def list_things() -> dict[str, str]:  # pragma: no cover - never called
        return {}

    with pytest.raises(RuntimeError, match=r"'/things' has no explicit operation_id"):
        assert_contract_operation_ids(app)


def test_duplicate_operation_ids_are_rejected() -> None:
    app = FastAPI()

    @app.get("/a", operation_id="things_read")
    def read_a() -> dict[str, str]:  # pragma: no cover - never called
        return {}

    @app.get("/b", operation_id="things_read")
    def read_b() -> dict[str, str]:  # pragma: no cover - never called
        return {}

    with pytest.raises(RuntimeError, match=r"duplicate operation_id 'things_read'"):
        assert_contract_operation_ids(app)


def test_schema_excluded_routes_are_not_constrained() -> None:
    app = FastAPI()

    @app.get("/internal", include_in_schema=False)
    def internal() -> dict[str, str]:  # pragma: no cover - never called
        return {}

    assert_contract_operation_ids(app)
