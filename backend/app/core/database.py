"""SQLAlchemy 2 database core (ADR-007: sync-first engine, psycopg 3).

Transaction discipline (docs/02, docs/03): application services own the
business transaction; repositories never call ``commit``. The request-scoped
session is provided by the ``get_session`` dependency and is never shared
across concurrent tasks.
"""

from collections.abc import Iterator

import structlog
from fastapi import Request
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import Settings

_logger = structlog.get_logger("app.database")

# Deterministic constraint names: fixed before the first table exists so
# every Alembic migration (and its forward fix) can reference constraints by
# stable, predictable names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all persistence models (first models: Milestone 2)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_database_engine(settings: Settings) -> Engine:
    """Lazily connecting engine; a bounded connect timeout keeps readiness
    probes and startup failures fast instead of hanging."""
    return create_engine(
        settings.database_url_str,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 2},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)


def get_session(request: Request) -> Iterator[Session]:
    """Request-scoped session dependency.

    Consumers (application services, from Milestone 2) own commit/rollback;
    the dependency only guarantees the session is closed.
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def check_database(engine: Engine) -> bool:
    """Cheap readiness check: can we obtain a connection and run SELECT 1?"""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        _logger.warning("database_check_failed", error=type(exc).__name__)
        return False
    return True
