"""Application factory.

Run in development with:

    uv run uvicorn app.main:create_app --factory --reload
"""

from fastapi import FastAPI

from app.api.health import health_router
from app.api.router import api_v1_router
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.settings import Settings, load_settings


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
    )
    app.state.settings = settings

    # Outermost middleware runs first: the correlation ID must exist before
    # the request log event is emitted.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix="/api/v1")
    return app
