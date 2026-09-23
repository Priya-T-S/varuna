"""
Database session management (SQLAlchemy).

Engine creation is lazy so the API can start (and unit tests can run)
without a database — endpoints that need the DB acquire a session via
the `get_db` dependency. The default URL is a local SQLite file; set
DATABASE_URL (or USE_POSTGRES=true) for PostgreSQL/PostGIS.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def _engine():
    from app.db.models import Base

    url = settings.database_url
    if url.startswith("sqlite"):
        # The alert monitor runs in a worker thread; SQLite must allow that.
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(url, pool_pre_ping=True)
    # Tables are created on first use so the app also works when the
    # lifespan hook has not run (e.g. TestClient without a context manager).
    Base.metadata.create_all(engine)
    _add_missing_columns(engine, Base)
    return engine


def _add_missing_columns(engine, base) -> None:
    """Additive migration: create_all() never alters existing tables, so add any
    column the ORM defines but an older database lacks. Only nullable columns
    are added, which is safe on SQLite and PostgreSQL."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or not column.nullable:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {col_type}'))
                logger.info("Migrated: added %s.%s", table.name, column.name)


@lru_cache
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create the application tables (idempotent)."""
    _engine()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped DB session."""
    db = _session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session for background work: commits on success, rolls back on error."""
    db = _session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
