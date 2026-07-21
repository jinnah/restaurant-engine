"""API cache policy and its one approved exception (M2A ADR-010; M3D ADR-017).

``NoStoreApiMiddleware`` is the single authority for ``Cache-Control`` on
``/api/v1``. These tests pin the exception to exactly what was approved —
successful delivery from the one registered public media-file route — and
prove the three properties that make it safe:

* it is decided by the middleware, never by trusting a downstream header;
* it is scoped by method and status;
* it is scoped by **route identity**, so no path that merely *looks* like
  the media route can obtain it. The adversarial cases below are synthetic
  routes that a prefix matcher would have granted immutable public caching.

Synthetic apps are used so hostile routes can exist without adding them to
the real application.
"""

from typing import Any

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core.cache_control import PUBLIC_MEDIA_CACHE_CONTROL, NoStoreApiMiddleware
from app.domains.media.public_service import PUBLIC_MEDIA_PATH_PREFIX

_MEDIA_ROUTE = f"{PUBLIC_MEDIA_PATH_PREFIX}{{asset_id}}/{{variant}}"
_MEDIA_PATH = f"{PUBLIC_MEDIA_PATH_PREFIX}an-asset/canonical"


def _app() -> FastAPI:
    """An app whose media-file route is the designated cacheable endpoint."""
    app = FastAPI()

    @app.api_route(_MEDIA_ROUTE, methods=["GET", "HEAD", "POST"])
    def media(asset_id: str, variant: str, status: int = 200) -> Response:
        del asset_id, variant
        return Response(b"bytes", status_code=status, media_type="image/webp")

    @app.get("/api/v1/private")
    def private() -> Response:
        # A route trying to grant itself caching must not succeed.
        return Response(
            b"{}", media_type="application/json", headers={"Cache-Control": "public, max-age=600"}
        )

    @app.get("/health/live")
    def health() -> Response:
        return Response(b"{}", media_type="application/json")

    app.add_middleware(NoStoreApiMiddleware, cacheable_endpoint=media)
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


class TestCachingIsScopedByRouteIdentity:
    """A path that merely resembles the media route must never be cached.

    Every case here returns a successful 200 from a GET, so method and
    status alone would allow caching; only route identity refuses it. Each
    one would have been granted immutable public caching by a prefix
    matcher.
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

        app.add_middleware(NoStoreApiMiddleware, cacheable_endpoint=media)
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

    def test_the_designated_route_still_is_cacheable_in_the_same_app(self) -> None:
        # Positive control: the negatives above are not passing because the
        # exception is broken outright.
        app = self._with_sibling(f"{PUBLIC_MEDIA_PATH_PREFIX}manifest")
        assert _cache_control(app, _MEDIA_PATH) == PUBLIC_MEDIA_CACHE_CONTROL

    def test_an_unmatched_path_has_no_endpoint_and_is_not_cached(self) -> None:
        assert _cache_control(_app(), "/api/v1/public/media/only-one-segment") == "no-store"


class TestRealApplicationWiring:
    """The composed application designates the real media handler."""

    def test_composed_app_wires_the_public_media_endpoint(self) -> None:
        from app.api.public_media_router import public_media_file_get
        from app.main import create_app
        from tests.conftest import make_settings

        app = create_app(make_settings())
        wired = [
            middleware
            for middleware in app.user_middleware
            if getattr(middleware.cls, "__name__", "") == NoStoreApiMiddleware.__name__
        ]
        assert len(wired) == 1
        assert wired[0].kwargs["cacheable_endpoint"] is public_media_file_get
