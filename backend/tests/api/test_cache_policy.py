"""API cache policy and its one approved exception (M2A ADR-010; M3D ADR-017).

``NoStoreApiMiddleware`` is the single authority for ``Cache-Control`` on
``/api/v1``. These tests pin the exception to exactly what was approved —
successful public media delivery — and prove the two properties that make
it safe: it is decided by the middleware (never by trusting a downstream
header), and it is scoped by path, method, and status.

A synthetic app is used so routes that deliberately set a hostile
``Cache-Control`` can exist without adding them to the real application.
"""

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.core.cache_control import (
    PUBLIC_MEDIA_CACHE_CONTROL,
    PUBLIC_MEDIA_PREFIX,
    NoStoreApiMiddleware,
)

_MEDIA_PATH = f"{PUBLIC_MEDIA_PREFIX}an-asset/canonical"


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/private")
    def private() -> Response:
        # A route trying to grant itself caching must not succeed.
        return Response(
            b"{}", media_type="application/json", headers={"Cache-Control": "public, max-age=600"}
        )

    @app.get("/health/live")
    def health() -> Response:
        return Response(b"{}", media_type="application/json")

    @app.api_route(_MEDIA_PATH, methods=["GET", "HEAD", "POST"])
    def media(status: int = 200) -> Response:
        return Response(b"bytes", status_code=status, media_type="image/webp")

    app.add_middleware(NoStoreApiMiddleware)
    return app


class TestGlobalNoStore:
    def test_api_responses_are_no_store(self) -> None:
        with TestClient(_app()) as client:
            assert client.get("/api/v1/private").headers["cache-control"] == "no-store"

    def test_a_route_cannot_grant_itself_caching(self) -> None:
        # The middleware overwrites rather than respecting a downstream
        # header: no authenticated route can opt out of the global policy,
        # by accident or otherwise.
        with TestClient(_app()) as client:
            response = client.get("/api/v1/private")
            assert "max-age" not in response.headers["cache-control"]

    def test_non_api_paths_are_untouched(self) -> None:
        with TestClient(_app()) as client:
            assert "cache-control" not in client.get("/health/live").headers


class TestPublicMediaException:
    def test_successful_get_is_publicly_cacheable_for_one_hour(self) -> None:
        with TestClient(_app()) as client:
            response = client.get(_MEDIA_PATH)
            assert response.headers["cache-control"] == PUBLIC_MEDIA_CACHE_CONTROL
            assert response.headers["cache-control"] == "public, max-age=3600, immutable"

    def test_successful_head_is_publicly_cacheable(self) -> None:
        with TestClient(_app()) as client:
            assert client.head(_MEDIA_PATH).headers["cache-control"] == PUBLIC_MEDIA_CACHE_CONTROL

    def test_not_modified_is_publicly_cacheable(self) -> None:
        with TestClient(_app()) as client:
            response = client.get(_MEDIA_PATH, params={"status": 304})
            assert response.status_code == 304
            assert response.headers["cache-control"] == PUBLIC_MEDIA_CACHE_CONTROL

    def test_every_error_status_stays_no_store(self) -> None:
        with TestClient(_app()) as client:
            for status in (400, 404, 405, 500, 503):
                response = client.get(_MEDIA_PATH, params={"status": status})
                assert response.headers["cache-control"] == "no-store", status

    def test_unsafe_methods_on_the_media_path_stay_no_store(self) -> None:
        with TestClient(_app()) as client:
            assert client.post(_MEDIA_PATH).headers["cache-control"] == "no-store"

    def test_the_exception_does_not_leak_to_neighbouring_public_paths(self) -> None:
        # Only the media prefix is cacheable; the menu and site projections
        # change with every administrative edit and stay no-store.
        app = FastAPI()

        @app.get("/api/v1/public/menu")
        def menu() -> Response:
            return Response(b"{}", media_type="application/json")

        @app.get("/api/v1/public/mediaish")
        def lookalike() -> Response:
            return Response(b"{}", media_type="application/json")

        app.add_middleware(NoStoreApiMiddleware)
        with TestClient(app) as client:
            assert client.get("/api/v1/public/menu").headers["cache-control"] == "no-store"
            assert client.get("/api/v1/public/mediaish").headers["cache-control"] == "no-store"
