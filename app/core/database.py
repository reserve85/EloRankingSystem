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
    import logging
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    logger = logging.getLogger(__name__)

    try:
        alembic_cfg = Config("alembic.ini")

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        if "alembic_version" in existing_tables:
            # Alembic is already tracking this database — just run pending migrations
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations applied successfully.")
        elif existing_tables:
            # Database has tables but no alembic_version (pre-Alembic database).
            # Stamp current state as head, then run any new migrations.
            logger.info("Existing database found without Alembic tracking. Stamping to head...")
            command.stamp(alembic_cfg, "head")
            command.upgrade(alembic_cfg, "head")
            logger.info("Database stamped and migrations applied successfully.")
        else:
            # Fresh database — run all migrations from scratch
            command.upgrade(alembic_cfg, "head")
            logger.info("Fresh database created and migrations applied successfully.")
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")
        # Fallback: create tables via SQLAlchemy for fresh databases
        Base.metadata.create_all(bind=engine)
        logger.warning("Fell back to create_all() for table creation.")
