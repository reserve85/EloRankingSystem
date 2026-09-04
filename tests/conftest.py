"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app

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


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

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
    """Create a test client with database dependency override."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
