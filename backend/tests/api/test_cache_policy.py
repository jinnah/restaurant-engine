"""API cache policy and its approved exceptions (M2A ADR-010; M3D ADR-017;
M4C ADR-020).

``NoStoreApiMiddleware`` is the single authority for ``Cache-Control`` on
``/api/v1``. These tests pin the exceptions to exactly what was approved —
successful delivery from the one registered public media-file route
(``public, max-age=3600, immutable`` on 200/304) and the successful public
storefront projection (``public, max-age=60`` on 200 only) — and prove the
three properties that make them safe:

* they are decided by the middleware, never by trusting a downstream
  header;
* they are scoped by method and per-endpoint status set;
* they are scoped by **route identity**, so no path that merely *looks*
  like a cacheable route can obtain a grant. The adversarial cases below
  are synthetic routes that a prefix matcher would have granted caching.

Synthetic apps are used so hostile routes can exist without adding them to
the real application.
"""

from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core.cache_control import (
    PUBLIC_MEDIA_CACHE_CONTROL,
    PUBLIC_MEDIA_POLICY,
    PUBLIC_STOREFRONT_CACHE_CONTROL,
    PUBLIC_STOREFRONT_POLICY,
    NoStoreApiMiddleware,
)
from app.domains.media.public_service import PUBLIC_MEDIA_PATH_PREFIX

_MEDIA_ROUTE = f"{PUBLIC_MEDIA_PATH_PREFIX}{{asset_id}}/{{variant}}"
_MEDIA_PATH = f"{PUBLIC_MEDIA_PATH_PREFIX}an-asset/canonical"
_STOREFRONT_PATH = "/api/v1/public/storefront"


def _app() -> FastAPI:
    """An app wiring both approved cacheable endpoints, like the real one."""
    app = FastAPI()

    @app.api_route(_MEDIA_ROUTE, methods=["GET", "HEAD", "POST"])
    def media(asset_id: str, variant: str, status: int = 200) -> Response:
        del asset_id, variant
        return Response(b"bytes", status_code=status, media_type="image/webp")

    @app.api_route(_STOREFRONT_PATH, methods=["GET", "HEAD", "POST"])
    def storefront(status: int = 200) -> Response:
        return Response(b"{}", status_code=status, media_type="application/json")

    @app.get("/api/v1/private")
    def private() -> Response:
        # A route trying to grant itself caching must not succeed.
        return Response(
            b"{}", media_type="application/json", headers={"Cache-Control": "public, max-age=600"}
        )

    @app.get("/health/live")
    def health() -> Response:
        return Response(b"{}", media_type="application/json")

    app.add_middleware(
        NoStoreApiMiddleware,
        cacheable_endpoints={media: PUBLIC_MEDIA_POLICY, storefront: PUBLIC_STOREFRONT_POLICY},
    )
    return app


def _cache_control(app: FastAPI, path: str, method: str = "GET", **kwargs: Any) -> str | None:
    with TestClient(app) as client:
        value = client.request(method, path, **kwargs).headers.get("cache-control")
    return str(value) if value is not None else None


class TestGlobalNoStore:
    def test_api_responses_are_no_store(self) -> None:
        assert _cache_control(_app(), "/api/v1/private") == "no-store"

    def test_a_route_cannot_grant_itself_caching(self) -> None:
        # The middleware overwrites rather than respecting a downstream
        # header: no authenticated route can opt out of the global policy,
        # by accident or otherwise.
        assert "max-age" not in str(_cache_control(_app(), "/api/v1/private"))

    def test_non_api_paths_are_untouched(self) -> None:
        assert _cache_control(_app(), "/health/live") is None


class TestPublicMediaException:
    def test_successful_get_is_publicly_cacheable_for_one_hour(self) -> None:
        assert _cache_control(_app(), _MEDIA_PATH) == PUBLIC_MEDIA_CACHE_CONTROL
        assert PUBLIC_MEDIA_CACHE_CONTROL == "public, max-age=3600, immutable"

    def test_successful_head_is_publicly_cacheable(self) -> None:
        assert _cache_control(_app(), _MEDIA_PATH, "HEAD") == PUBLIC_MEDIA_CACHE_CONTROL

    def test_not_modified_is_publicly_cacheable(self) -> None:
        assert (
            _cache_control(_app(), _MEDIA_PATH, params={"status": 304})
            == PUBLIC_MEDIA_CACHE_CONTROL
        )

    def test_every_error_status_stays_no_store(self) -> None:
        app = _app()
        for status in (400, 404, 405, 422, 500, 503):
            assert _cache_control(app, _MEDIA_PATH, params={"status": status}) == "no-store", status

    def test_unsafe_methods_on_the_media_route_stay_no_store(self) -> None:
        assert _cache_control(_app(), _MEDIA_PATH, "POST") == "no-store"


class TestPublicStorefrontException:
    """The M4C grant (ADR-020 §12): sixty seconds, 200 only, no immutable."""

    def test_successful_get_is_publicly_cacheable_for_one_minute(self) -> None:
        assert _cache_control(_app(), _STOREFRONT_PATH) == PUBLIC_STOREFRONT_CACHE_CONTROL
        assert PUBLIC_STOREFRONT_CACHE_CONTROL == "public, max-age=60"

    def test_the_projection_is_never_immutable(self) -> None:
        # Publication replaces the representation in place, so the sixty
        # second bound is the whole grant — immutable would pin stale
        # content past every freshness guarantee ADR-020 §12 makes.
        assert "immutable" not in PUBLIC_STOREFRONT_CACHE_CONTROL

    def test_successful_head_is_publicly_cacheable(self) -> None:
        assert _cache_control(_app(), _STOREFRONT_PATH, "HEAD") == PUBLIC_STOREFRONT_CACHE_CONTROL

    def test_not_modified_is_not_in_the_storefront_grant(self) -> None:
        # Unlike media there is no validator on the projection, so 304 was
        # never approved for it: statuses are per-endpoint, not global.
        assert _cache_control(_app(), _STOREFRONT_PATH, params={"status": 304}) == "no-store"

    def test_every_error_status_stays_no_store(self) -> None:
        app = _app()
        for status in (400, 404, 405, 422, 500, 503):
            assert _cache_control(app, _STOREFRONT_PATH, params={"status": status}) == "no-store", (
                status
            )

    def test_unsafe_methods_on_the_storefront_route_stay_no_store(self) -> None:
        assert _cache_control(_app(), _STOREFRONT_PATH, "POST") == "no-store"


class TestCachingIsScopedByRouteIdentity:
    """A path that merely resembles a cacheable route must never be cached.

    Every case here returns a successful 200 from a GET, so method and
    status alone would allow caching; only route identity refuses it. Each
    one would have been granted public caching by a prefix matcher.
    """

    @staticmethod
    def _with_sibling(path: str) -> FastAPI:
        app = FastAPI()

        @app.get(_MEDIA_ROUTE)
        def media(asset_id: str, variant: str) -> Response:
            del asset_id, variant
            return Response(b"bytes", media_type="image/webp")

        @app.get(path)
        def sibling(**_params: str) -> Response:
            return Response(b"{}", media_type="application/json")

        app.add_middleware(NoStoreApiMiddleware, cacheable_endpoints={media: PUBLIC_MEDIA_POLICY})
        return app

    def test_single_segment_sibling_under_the_media_prefix(self) -> None:
        path = f"{PUBLIC_MEDIA_PATH_PREFIX}manifest"
        assert _cache_control(self._with_sibling(path), path) == "no-store"

    def test_deeper_route_below_the_media_template(self) -> None:
        app = self._with_sibling(f"{_MEDIA_ROUTE}/extra")
        assert _cache_control(app, f"{_MEDIA_PATH}/extra") == "no-store"

    def test_lookalike_prefix_route(self) -> None:
        app = self._with_sibling("/api/v1/public/mediaevil/{asset_id}/{variant}")
        assert _cache_control(app, "/api/v1/public/mediaevil/an-asset/canonical") == "no-store"

    def test_unrelated_public_route(self) -> None:
        app = self._with_sibling("/api/v1/public/menu")
        assert _cache_control(app, "/api/v1/public/menu") == "no-store"

    def test_storefront_lookalike_route_is_not_cacheable(self) -> None:
        # A sibling that impersonates the storefront path in an app where
        # only the media endpoint holds a grant: the path is exactly the
        # cacheable one elsewhere, but this handler was never wired.
        app = self._with_sibling(_STOREFRONT_PATH)
        assert _cache_control(app, _STOREFRONT_PATH) == "no-store"

    def test_the_designated_route_still_is_cacheable_in_the_same_app(self) -> None:
        # Positive control: the negatives above are not passing because the
        # exception is broken outright.
        app = self._with_sibling(f"{PUBLIC_MEDIA_PATH_PREFIX}manifest")
        assert _cache_control(app, _MEDIA_PATH) == PUBLIC_MEDIA_CACHE_CONTROL

    def test_an_unmatched_path_has_no_endpoint_and_is_not_cached(self) -> None:
        assert _cache_control(_app(), "/api/v1/public/media/only-one-segment") == "no-store"


class TestRealApplicationWiring:
    """The composed application designates exactly the two real handlers."""

    def test_composed_app_wires_both_public_endpoints(self) -> None:
        from app.api.public_media_router import public_media_file_get
        from app.domains.storefront.router_public import public_storefront_get
        from app.main import create_app
        from tests.conftest import make_settings

        app = create_app(make_settings())
        wired = [
            middleware
            for middleware in app.user_middleware
            if getattr(middleware.cls, "__name__", "") == NoStoreApiMiddleware.__name__
        ]
        assert len(wired) == 1
        endpoints = wired[0].kwargs["cacheable_endpoints"]
        assert endpoints == {
            public_media_file_get: PUBLIC_MEDIA_POLICY,
            public_storefront_get: PUBLIC_STOREFRONT_POLICY,
        }
