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
    """Initialize database tables and run Alembic migrations.

    Handles three scenarios:
    1. Fresh database (no tables): create all tables via SQLAlchemy, stamp as head.
    2. Existing database with alembic_version: run pending Alembic migrations.
    3. Existing database without alembic_version (pre-Alembic): stamp as head, then
       upgrade (to catch any new migrations added after the database was created).
    """
    import logging
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    logger = logging.getLogger(__name__)

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    alembic_cfg = Config("alembic.ini")

    if not existing_tables:
        # Scenario 1: Fresh database — create all tables and stamp as head
        logger.info("Fresh database detected. Creating all tables...")
        Base.metadata.create_all(bind=engine)
        try:
            command.stamp(alembic_cfg, "head")
            logger.info("Database created and stamped to head.")
        except Exception as e:
            logger.warning(f"Alembic stamp failed (non-critical): {e}")

    elif "alembic_version" in existing_tables:
        # Scenario 2: Alembic-tracked database — run pending migrations
        logger.info("Alembic-tracked database found. Running pending migrations...")
        try:
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations applied successfully.")
        except Exception as e:
            logger.error(f"Alembic upgrade failed: {e}")

    else:
        # Scenario 3: Pre-Alembic database — stamp and upgrade
        logger.info("Pre-Alembic database found. Stamping to head and checking for new migrations...")
        try:
            command.stamp(alembic_cfg, "head")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database stamped and migrations applied successfully.")
        except Exception as e:
            logger.error(f"Alembic stamp/upgrade failed: {e}")
