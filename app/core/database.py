"""Database configuration and session management."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.core.config import settings


# Ensure data directory exists
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)

# Also ensure the database file's parent directory exists (for absolute paths in Docker)
if "sqlite" in settings.database_url:
    db_path = settings.database_url.replace("sqlite:///", "").replace("sqlite:////", "/")
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=settings.app_debug,
)


# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite pragmas on connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def get_db() -> Session:
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables and run Alembic migrations."""
    from alembic.config import Config
    from alembic import command

    # First create any tables that don't exist yet (for fresh installs)
    Base.metadata.create_all(bind=engine)

    # Then run any pending Alembic migrations (for upgrades)
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        # If Alembic fails (e.g. missing migrations dir), log but don't crash
        import logging
        logging.getLogger(__name__).warning(f"Alembic migration skipped: {e}")
