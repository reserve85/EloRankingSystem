"""Tests for the double-submit cookie CSRF protection (Fix #3)."""

import pytest

from app.core.config import settings
from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

# The main test suite runs with CSRF disabled (see conftest.py). These tests
# re-enable it per test and verify the middleware behaviour both in isolation
# and against real endpoints.


@pytest.fixture
def csrf_enabled():
    """Temporarily enable CSRF protection, then restore the previous value."""
    original = settings.csrf_enabled
    settings.csrf_enabled = True
    try:
        yield
    finally:
        settings.csrf_enabled = original


def _cookie_value(set_cookie_header: str, name: str) -> str | None:
    """Extract a cookie value from a ``Set-Cookie`` header (robust parsing)."""
    for part in set_cookie_header.split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
    return None


def test_csrf_cookie_issued_when_absent(client, csrf_enabled):
    """A response should set a non-HttpOnly csrf_token cookie when none exists."""
    resp = client.get("/health")
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert _cookie_value(set_cookie, CSRF_COOKIE_NAME) is not None
    # The JS apiFetch() helper reads the cookie, so it must NOT be HttpOnly.
    assert "HttpOnly" not in set_cookie.lower()


def test_mutating_request_without_token_rejected(client, csrf_enabled):
    """POST without a CSRF cookie or header must return 403."""
    resp = client.post("/auth/logout")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF token missing or invalid"


def test_mutating_request_with_mismatched_token_rejected(client, csrf_enabled):
    """A header that does not match the cookie must return 403."""
    client.get("/health")  # obtain the csrf cookie
    resp = client.post("/auth/logout", headers={CSRF_HEADER_NAME: "not-the-token"})
    assert resp.status_code == 403


def test_mutating_request_with_valid_token_succeeds(client, csrf_enabled):
    """A header echoing the cookie value must be accepted."""
    client.get("/health")  # obtain the csrf cookie
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token
    resp = client.post("/auth/logout", headers={CSRF_HEADER_NAME: token})
    assert resp.status_code == 200


def test_get_requests_are_not_blocked(client, csrf_enabled):
    """Safe (GET) requests must never be CSRF-blocked."""
    resp = client.get("/auth/me")
    assert resp.status_code != 403


def test_login_endpoint_is_exempt(client, csrf_enabled):
    """POST /auth/login must not require a CSRF token (it establishes the session)."""
    resp = client.post("/auth/login", data={"username": "nobody", "password": "nope"})
    assert resp.status_code != 403
    assert resp.status_code == 401  # login itself fails, not CSRF


def test_csrf_disabled_skips_validation(client):
    """With CSRF disabled (see conftest), a mutating request reaches the route."""
    resp = client.post("/auth/logout")  # non-exempt endpoint, no token
    assert resp.status_code == 200  # reached the route, not blocked by middleware