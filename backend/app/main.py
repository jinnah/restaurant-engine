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
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.openapi import assert_contract_operation_ids
from app.core.settings import Settings, load_settings


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

    # Outermost middleware runs first: the correlation ID must exist before
    # the request log event is emitted.
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
