"""Permanent invariants for the public API surface (M3D, ADR-013 amendment).

The host guard exempts ``GET``/``HEAD`` under ``/api/v1/public/`` from the
known-Host check, and that exemption is only safe because every route there
resolves the Business from the Host itself. This module turns that
"only because" into a test: a public read route that forgets
``resolve_public_business`` fails the suite instead of silently shipping a
Host-independent endpoint.

The walk inspects the FastAPI ``Dependant`` graph, so it sees dependencies
declared anywhere in the effective chain (parameter defaults, router-level
``dependencies=``, nested sub-dependencies) and covers schema-hidden routes
— the M3D companion ``HEAD`` routes are checked exactly like their ``GET``
counterparts. Routes are enumerated through ``iter_route_contracts`` so the
effective (prefixed) paths are compared, matching what the guard sees.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.dependencies.models import Dependant

from app.core.host_guard import PUBLIC_EXEMPT_METHODS, PUBLIC_PATH_PREFIX
from app.core.openapi import iter_route_contracts
from app.domains.businesses.resolution import resolve_public_business
from app.domains.media.public_service import PUBLIC_MEDIA_PATH_PREFIX, public_media_url
from app.main import create_app
from tests.conftest import make_settings


def _effective_calls(dependant: Dependant) -> set[Callable[..., Any]]:
    """Every callable in a route's effective dependency graph."""
    calls: set[Callable[..., Any]] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        if current.call is not None:
            calls.add(current.call)
        stack.extend(current.dependencies)
    return calls


def _public_read_routes(app: FastAPI) -> list[Any]:
    """Registered public routes serving an exempt (safe) method.

    Deliberately does **not** filter on ``include_in_schema``: the guard
    exempts by path and method, so schema-hidden routes must satisfy the
    same invariant.
    """
    return [
        route
        for route in iter_route_contracts(app)
        if route.path.startswith(PUBLIC_PATH_PREFIX)
        and bool(set(route.methods or set()) & PUBLIC_EXEMPT_METHODS)
    ]


class TestPublicRoutesResolveTheirTenant:
    def test_every_public_read_route_depends_on_the_host_resolver(self) -> None:
        app = create_app(make_settings())
        routes = _public_read_routes(app)
        # Positive control: an empty list would make the assertion vacuous
        # (e.g. if the prefix constant ever changed without this test).
        assert routes, "no public read routes found under the exempt prefix"
        for route in routes:
            calls = _effective_calls(route.dependant)
            assert resolve_public_business in calls, (
                f"public route '{route.path}' ({sorted(route.methods or set())}) does not"
                " resolve the Business from the Host; the host-guard exemption"
                " (ADR-013 amendment) requires it"
            )

    def test_schema_hidden_public_routes_are_inspected(self) -> None:
        # The invariant must not be satisfiable by hiding a route from the
        # OpenAPI schema: a hidden route is still routable and still exempt.
        app = FastAPI()

        @app.get(f"{PUBLIC_PATH_PREFIX}thing", include_in_schema=False)
        def hidden() -> dict[str, str]:  # pragma: no cover - never called
            return {}

        routes = _public_read_routes(app)
        assert [route.path for route in routes] == [f"{PUBLIC_PATH_PREFIX}thing"]

    def test_the_check_detects_a_missing_resolver(self) -> None:
        # Negative control: the walk must actually be able to fail.
        app = FastAPI()

        @app.get(f"{PUBLIC_PATH_PREFIX}unresolved")
        def unresolved() -> dict[str, str]:  # pragma: no cover - never called
            return {}

        (route,) = _public_read_routes(app)
        assert resolve_public_business not in _effective_calls(route.dependant)

    def test_the_check_sees_nested_and_router_level_dependencies(self) -> None:
        # The resolver is usually a direct parameter dependency, but the walk
        # must find it through an intermediate dependency too.
        def wrapper(business: Annotated[Any, Depends(resolve_public_business)]) -> Any:
            return business  # pragma: no cover - never called

        app = FastAPI()

        @app.get(f"{PUBLIC_PATH_PREFIX}nested")
        def nested(_value: Annotated[Any, Depends(wrapper)]) -> dict[str, str]:  # pragma: no cover
            return {}

        (route,) = _public_read_routes(app)
        assert resolve_public_business in _effective_calls(route.dependant)


class TestPublicMediaPathHasOneDefinition:
    """The registered route and the composed URLs share one definition.

    Two places need the public media path: the route registration and the
    URLs the menu projection composes. If they drifted, a menu would
    advertise URLs that 404 — so the constant is pinned to the registered
    route here.

    This is now **defense in depth only**. The cache policy no longer
    consumes the path at all: it is granted by route identity, so breaking
    or removing this invariant cannot widen caching (M3D correction C2).
    """

    def test_registered_route_matches_the_shared_prefix(self) -> None:
        app = create_app(make_settings())
        media_routes = [
            route
            for route in iter_route_contracts(app)
            if route.path.startswith(PUBLIC_MEDIA_PATH_PREFIX)
        ]
        assert {route.operation_id for route in media_routes} == {"public_media_file_get", None}
        assert all(
            route.path == f"{PUBLIC_MEDIA_PATH_PREFIX}{{asset_id}}/{{variant}}"
            for route in media_routes
        )

    def test_composed_urls_address_the_registered_route(self) -> None:
        asset_id = uuid.uuid4()
        url = public_media_url(asset_id, "w320")
        assert url == f"{PUBLIC_MEDIA_PATH_PREFIX}{asset_id}/w320"
        # Relative, same-origin, and free of storage detail.
        assert url.startswith("/api/v1/")
        assert not url.startswith("http")


class TestPublicExemptionIsMethodScoped:
    def test_only_safe_methods_are_exempt(self) -> None:
        assert PUBLIC_EXEMPT_METHODS == {"GET", "HEAD"}

    def test_public_routes_serve_only_exempt_methods(self) -> None:
        # If an unsafe public route is ever added, it would sit behind the
        # host guard while its siblings do not — a contract split that must
        # be an explicit, reviewed decision rather than an accident.
        app = create_app(make_settings())
        unsafe = [
            (route.path, sorted(set(route.methods or set()) - PUBLIC_EXEMPT_METHODS))
            for route in iter_route_contracts(app)
            if route.path.startswith(PUBLIC_PATH_PREFIX)
            and set(route.methods or set()) - PUBLIC_EXEMPT_METHODS
        ]
        assert unsafe == []
