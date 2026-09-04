"""Tests for the slowapi rate limiting on authentication endpoints (Fix #4).

The general suite runs with rate limiting disabled (see conftest.py). These
tests re-enable the limiter per test and verify the configured limits, then
restore and reset the limiter counters.
"""

import pytest

from app.core.rate_limit import limiter
from app.models.user import User, UserRole
from app.auth.password import hash_password

LOGIN_LIMIT = 20
AUTO_LOGIN_LIMIT = 30
PASSWORD_LIMIT = 5


@pytest.fixture
def rate_limiting_enabled():
    """Enable the global limiter, clear counters, and restore afterwards."""
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = False


def _login_ok(client, username: str, password: str):
    """Helper: POST a valid login so the client stores the auth cookie."""
    resp = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert resp.status_code == 200


class TestLoginRateLimit:
    """POST /auth/login is limited to 20 requests/minute."""

    def test_exceeded_after_20_attempts(self, client, db_session, rate_limiting_enabled):
        for _ in range(LOGIN_LIMIT):
            resp = client.post(
                "/auth/login", data={"username": "nobody", "password": "nope"}
            )
            assert resp.status_code == 401  # route reached, no token burned on CSRF

        resp = client.post(
            "/auth/login", data={"username": "nobody", "password": "nope"}
        )
        assert resp.status_code == 429


class TestAutoLoginRateLimit:
    """GET /auth/auto-login is limited to 30 requests/minute."""

    def test_exceeded_after_30_attempts(self, client, db_session, rate_limiting_enabled):
        for _ in range(AUTO_LOGIN_LIMIT):
            resp = client.get("/auth/auto-login", params={"u": "nobody", "p": "nope"})
            assert resp.status_code != 429

        resp = client.get("/auth/auto-login", params={"u": "nobody", "p": "nope"})
        assert resp.status_code == 429


class TestPasswordChangeRateLimit:
    """POST /password/change is limited to 5 requests/minute."""

    def test_exceeded_after_5_attempts(self, client, db_session, rate_limiting_enabled):
        user = User(
            username="ratelimited",
            password_hash=hash_password("Password1!"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()
        _login_ok(client, "ratelimited", "Password1!")

        body = {
            "current_password": "wrong-password",
            "new_password": "NewPassword1!",
            "confirm_new_password": "NewPassword1!",
        }
        for _ in range(PASSWORD_LIMIT):
            resp = client.post("/password/change", json=body)
            assert resp.status_code == 200  # route reached, wrong password -> success=False

        resp = client.post("/password/change", json=body)
        assert resp.status_code == 429


class TestPasswordResetRateLimit:
    """POST /password/reset is limited to 5 requests/minute."""

    def test_exceeded_after_5_attempts(self, client, db_session, rate_limiting_enabled):
        admin = User(
            username="ratelimitadmin",
            password_hash=hash_password("Password1!"),
            role=UserRole.ADMIN,
            active=True,
        )
        target = User(
            username="targetuser",
            password_hash=hash_password("Password1!"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add_all([admin, target])
        db_session.commit()
        _login_ok(client, "ratelimitadmin", "Password1!")

        body = {
            "user_id": target.id,
            "new_password": "NewPassword1!",
            "confirm_new_password": "NewPassword1!",
        }
        for _ in range(PASSWORD_LIMIT):
            resp = client.post("/password/reset", json=body)
            assert resp.status_code == 200  # route reached, resets succeed until limit

        resp = client.post("/password/reset", json=body)
        assert resp.status_code == 429


class TestRateLimitingToggle:
    """The limiter respects the global enabled flag (used by the test suite)."""

    def test_disabled_by_default_allows_requests(self, client, db_session):
        """Without the fixture, the limiter is disabled and login is not blocked."""
        assert limiter.enabled is False
        resp = client.post(
            "/auth/login", data={"username": "nobody", "password": "nope"}
        )
        assert resp.status_code == 401

    def test_enabled_flag_controls_enforcement(self, client, db_session, rate_limiting_enabled):
        assert limiter.enabled is True
        # Just verify the flag is toggled; a single request is still within limits.
        resp = client.post(
            "/auth/login", data={"username": "nobody", "password": "nope"}
        )
        assert resp.status_code == 401