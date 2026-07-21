"""Contract-level OpenAPI guarantees (ADR-009).

Operation IDs are public API contracts: the generated TypeScript client
derives stable names from them, so they must never fall back to FastAPI's
function-name-derived defaults. Every schema-visible route declares an
explicit ``operation_id``, validated at application composition time — a
violating process never starts, so the rule enforces itself for every
future route.

Enumerating the composed application's routes is not simply iterating
``app.routes``: this FastAPI version does not flatten ``include_router``
into ``APIRoute`` objects on the application. It stores an *included
router* wrapper that resolves its members lazily, so ``app.routes``
contains no ``APIRoute`` at all for routes mounted through a router.
``iter_route_contracts`` walks that structure (and a flattened structure,
should a future version return to one), which is why the validator below
actually sees the 55+ routes it is meant to police.
"""

from collections.abc import Iterable, Iterator
from typing import Any, Protocol, runtime_checkable

from fastapi import FastAPI
from fastapi.routing import APIRoute


@runtime_checkable
class RouteContract(Protocol):
    """The route attributes the contract checks depend on.

    Satisfied both by ``APIRoute`` and by the per-route context objects a
    wrapped included router resolves to, so callers never depend on which
    composition strategy the installed FastAPI uses.
    """

    path: str
    operation_id: str | None
    include_in_schema: bool
    dependant: Any

    @property
    def methods(self) -> Any: ...  # pragma: no cover - structural only


def _is_route_contract(candidate: object) -> bool:
    return all(
        hasattr(candidate, name)
        for name in ("path", "methods", "operation_id", "include_in_schema", "dependant")
    )


def _walk(routes: Iterable[Any]) -> Iterator[Any]:
    for route in routes:
        # An included-router wrapper resolves to its member routes lazily.
        resolve = getattr(route, "effective_route_contexts", None)
        if callable(resolve):
            yield from _walk(resolve())
            continue
        if isinstance(route, APIRoute) or _is_route_contract(route):
            yield route


def iter_route_contracts(app: FastAPI) -> Iterator[Any]:
    """Every API route of the composed app, with effective paths.

    Plain Starlette routes (``/openapi.json``, ``/docs``) carry no
    dependency graph and are deliberately excluded — they are framework
    surface, not API contract.
    """
    yield from _walk(app.routes)


def assert_contract_operation_ids(app: FastAPI) -> None:
    """Fail fast unless every schema-visible route has a unique explicit id.

    Called by ``create_app`` after all routers are included. Renaming a
    handler function can therefore never change the contract; changing an
    ``operation_id`` itself is a deliberate, reviewed breaking change that
    surfaces as a generated-client diff (ADR-009).

    Schema-hidden routes are exempt: they are not part of the generated
    client (the M3D companion ``HEAD`` routes are the first such routes,
    sharing their ``GET`` sibling's handler and contributing no operation).
    """
    seen: dict[str, str] = {}
    for route in iter_route_contracts(app):
        if not route.include_in_schema:
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
