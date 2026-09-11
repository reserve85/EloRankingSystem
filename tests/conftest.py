"""Pytest configuration and shared fixtures."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set a clean, throwaway environment BEFORE importing any app module, so that
# app.core.config / app.core.database build their engines and directories from
# test values instead of the production defaults. Without this, importing the
# app (and starting the TestClient lifespan) would create `data/`,
# `data/database.db` and the CWD-relative `test.db` files in the working tree.
# Fix M1: the whole suite now runs against a true in-memory SQLite database.
# The imports below are intentionally after this block (E402): the env vars
# must be in place before the app modules read them.
_TEST_ROOT = tempfile.mkdtemp(prefix="elo-pytest-")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("DATA_DIR", os.path.join(_TEST_ROOT, "data"))
os.environ.setdefault("UPLOAD_DIR", os.path.join(_TEST_ROOT, "uploads"))

from app.core.database import Base, get_db  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.main import app  # noqa: E402

# The CSRF middleware is part of the app. Existing tests hit state-changing
# endpoints directly without a CSRF token, so disable enforcement for the
# general suite. Dedicated CSRF coverage lives in tests/test_csrf.py, which
# re-enables it per test.
settings.csrf_enabled = False

# The slowapi rate limiter is also part of the app. Existing tests exercise
# auth endpoints more than the production limits would allow, so disable
# enforcement for the general suite. Dedicated rate-limit coverage lives in
# tests/test_rate_limit.py, which re-enables it per test. `limiter.enabled`
# is read at request time, so toggling here takes effect immediately.
settings.rate_limit_enabled = False
limiter.enabled = False


@pytest.fixture(autouse=True)
def _restore_settings_state():
    """L5: stop global settings mutations from leaking across tests..

    The shared ``settings`` singleton and the slowapi ``limiter.enabled`` flag are
    snapshotted before each test and restored after it. Dedicated tests (test_csrf.py,
    test_rate_limit.py, test_proxy_headers.py) may temporarily toggle these;the
    autouse restore guarantees no mutation survives into a later test, regardless
    of import order. The baseline snapshot takes the suite-wide defaults (CSRF and
    rate limiting disabled` above, so those defaults persist for the general suite..
    """
    saved_state = vars(settings).copy()
    saved_limiter_enabled = limiter.enabled
    yield
    settings.__dict__.clear()
    settings.__dict__.update(saved_state)
    limiter.enabled = saved_limiter_enabled


# True in-memory SQLite, shared by every session through a single pooled
# connection. A plain "sqlite://" engine creates a *fresh* in-memory database
# per connection, so StaticPool is required to make all sessions/connections
# see the same data. This is what keeps the suite from leaving *.db files
# behind (Fix M1).
TEST_DATABASE_URL = "sqlite://"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Mirror the production engine's SQLite pragmas (Fix M4): the production engine
# enables ``PRAGMA foreign_keys=ON`` (app/core/database.py) but the test engine
# historically did not, so the suite could never observe foreign-key violations
# (e.g. deleting a user who authored matches). Register the same pragma here so
# tests exercise the same constraints the running app enforces.
from sqlalchemy import event  # noqa: E402


@event.listens_for(test_engine, "connect")
def _set_test_sqlite_pragma(dbapi_connection, connection_record):
    """Enable SQLite foreign keys on every test-engine connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Drop first to purge any stale data from a crashed previous run
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database dependency override.

    The application lifespan (``init_db()`` + ``provision_system_user()``) is
    stubbed so that starting the TestClient never touches the production
    engine or the working tree (Fix M1). The test-database schema is managed
    exclusively by the ``db_session`` fixture.
    """
    import app.main as main_module

    app.dependency_overrides[get_db] = override_get_db
    original_init_db = main_module.init_db
    original_provision = main_module.provision_system_user
    original_prune = main_module.prune_audit_log
    main_module.init_db = lambda *args, **kwargs: None
    main_module.provision_system_user = lambda *args, **kwargs: None
    main_module.prune_audit_log = lambda *args, **kwargs: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        main_module.init_db = original_init_db
        main_module.provision_system_user = original_provision
        main_module.prune_audit_log = original_prune
