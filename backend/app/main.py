"""Application factory.

Run in development with:

    uv run uvicorn app.main:create_app --factory --reload
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import health_router
from app.api.router import api_v1_router
from app.core.cache_control import NoStoreApiMiddleware
from app.core.correlation import CorrelationIdMiddleware
from app.core.database import create_database_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.core.host_guard import KnownHostGuardMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.openapi import assert_contract_operation_ids
from app.core.settings import Settings, load_settings
from app.domains.media.storage import LocalFilesystemStorage


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Compose the FastAPI application from validated settings.

    Tests pass an explicit ``Settings``; the development server and
    production entrypoint load settings from the environment.
    """
    settings = settings if settings is not None else load_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Restaurant Engine API",
        version="0.0.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    # The engine connects lazily; creating it requires no running database.
    engine = create_database_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # Media storage (M3C). Production requires the configured root to exist
    # and be writable (fail-fast probe); development/test create the
    # gitignored default lazily so the dev stack needs no manual setup.
    media_root = settings.media_storage_root_path
    media_storage = LocalFilesystemStorage(media_root)
    if settings.is_production:
        media_storage.startup_check()
    else:
        media_root.mkdir(parents=True, exist_ok=True)
    app.state.media_storage = media_storage
    # The upload worker's processing scratch location is supplied through
    # composition, NOT read off the storage object (final correction 2): the
    # MediaStorage protocol is exactly put/open/delete/stat, so a future
    # provider adapter never needs a filesystem ``root``. It lives under the
    # local root's ``.tmp`` today; the sweep's stale-temp cleanup owns it.
    media_scratch_dir = media_root / ".tmp"
    if not settings.is_production:
        media_scratch_dir.mkdir(parents=True, exist_ok=True)
    app.state.media_scratch_dir = media_scratch_dir

    # add_middleware wraps outward, so the LAST call is the OUTERMOST layer.
    # Resulting order, outer → inner:
    #   NoStore → CorrelationId → RequestLogging → KnownHostGuard → app
    # so the host guard runs with a bound correlation id (its ADR-008 400
    # carries it), is logged like any request, and its /api/v1 rejections are
    # stamped no-store — while never running for exempt public/health paths.
    app.add_middleware(KnownHostGuardMiddleware, settings=settings)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    # API responses carry session/CSRF/account data: never cached (ADR-010).
    app.add_middleware(NoStoreApiMiddleware)

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix="/api/v1")

    # Operation IDs are client contracts (ADR-009): refuse to compose an app
    # whose schema-visible routes lack explicit, unique ids.
    assert_contract_operation_ids(app)
    return app
