"""Contract-level OpenAPI guarantees (ADR-009).

Operation IDs are public API contracts: the generated TypeScript client
derives stable names from them, so they must never fall back to FastAPI's
function-name-derived defaults. Every schema-visible route declares an
explicit ``operation_id``, validated at application composition time — a
violating process never starts, so the rule enforces itself for every
future route.
"""

from fastapi import FastAPI
from fastapi.routing import APIRoute


def assert_contract_operation_ids(app: FastAPI) -> None:
    """Fail fast unless every schema-visible route has a unique explicit id.

    Called by ``create_app`` after all routers are included. Renaming a
    handler function can therefore never change the contract; changing an
    ``operation_id`` itself is a deliberate, reviewed breaking change that
    surfaces as a generated-client diff (ADR-009).
    """
    seen: dict[str, str] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        operation_id = route.operation_id
        if operation_id is None:
            msg = (
                f"route '{route.path}' has no explicit operation_id; every "
                "schema-visible route must declare one (ADR-009)"
            )
            raise RuntimeError(msg)
        if operation_id in seen:
            msg = (
                f"duplicate operation_id '{operation_id}' on routes "
                f"'{seen[operation_id]}' and '{route.path}' (ADR-009)"
            )
            raise RuntimeError(msg)
        seen[operation_id] = route.path
