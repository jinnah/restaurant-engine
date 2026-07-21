"""Operation-ID contract enforcement (ADR-009).

Operation IDs feed the generated TypeScript client, so every schema-visible
route must declare one explicitly and they must be unique. The validator
runs inside ``create_app``; these tests prove both failure modes and that
the composed application passes.
"""

import pytest
from fastapi import FastAPI

from app.core.openapi import assert_contract_operation_ids, iter_route_contracts
from app.main import create_app
from tests.conftest import make_settings


def test_composed_application_passes_validation() -> None:
    # create_app already calls the validator; constructing without an
    # exception is the contract. Re-running it directly must also pass.
    app = create_app(make_settings())
    assert_contract_operation_ids(app)


def test_validation_actually_inspects_the_composed_routes() -> None:
    """The validator must not pass by seeing nothing (M3D regression guard).

    This FastAPI version does not flatten ``include_router`` into
    ``APIRoute`` objects on the application, so a naive ``app.routes``
    walk finds zero routes and every contract assertion above becomes
    vacuously true. Pin the enumeration to the schema instead: every
    schema-visible operation must be reachable through
    ``iter_route_contracts``.
    """
    app = create_app(make_settings())
    walked = {route.operation_id for route in iter_route_contracts(app) if route.include_in_schema}
    documented = {
        operation["operationId"]
        for path_item in app.openapi()["paths"].values()
        for operation in path_item.values()
    }
    assert walked == documented
    assert len(walked) > 1


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
