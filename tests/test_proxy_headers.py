"""Tests for trusted-proxy (X-Forwarded-For) handling (Fix M6)."""

from types import SimpleNamespace

from app.core.config import settings
from app.core.request import get_client_ip


class _FakeRequest:
    def __init__(self, host=None, xff=None):
        self.client = SimpleNamespace(host=host) if host else None
        self._xff = xff

    @property
    def headers(self):
        return SimpleNamespace(
            get=lambda name, default=None: (
                self._xff if name.lower() == "x-forwarded-for" else default
            )
        )


class TestGetClientIp:
    """get_client_ip must honor X-Forwarded-For only from trusted proxies."""

    def test_no_trusted_proxy_returns_peer(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", [])
        assert get_client_ip(_FakeRequest(host="1.2.3.4", xff="9.9.9.9")) == "1.2.3.4"

    def test_untrusted_peer_ignores_forwarded_header(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", ["5.6.7.8"])
        assert get_client_ip(_FakeRequest(host="1.2.3.4", xff="9.9.9.9")) == "1.2.3.4"

    def test_trusted_proxy_uses_rightmost_untrusted(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", ["5.6.7.8"])
        req = _FakeRequest(host="5.6.7.8", xff="1.2.3.4, 5.6.7.8")
        assert get_client_ip(req) == "1.2.3.4"

    def test_trusted_proxy_without_header_falls_back_to_peer(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", ["5.6.7.8"])
        assert get_client_ip(_FakeRequest(host="5.6.7.8", xff=None)) == "5.6.7.8"

    def test_all_forwarded_entries_trusted_falls_back_to_peer(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", "5.6.7.8")
        req = _FakeRequest(host="5.6.7.8", xff="5.6.7.8, 5.6.7.8")
        # Every forwarded entry is itself a trusted proxy -> no client found,
        # so the socket peer is kept.
        assert get_client_ip(req) == "5.6.7.8"

    def test_no_client_falls_back_to_loopback(self, monkeypatch):
        monkeypatch.setattr(settings, "trusted_proxies", [])
        assert get_client_ip(_FakeRequest(host=None)) == "127.0.0.1"

    def test_trusted_proxies_comma_string_from_env(self, monkeypatch):
        # TRUSTED_PROXIES is a comma-separated string; get_client_ip parses it.
        monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.1, 10.0.0.2")
        from app.core.config import Settings

        fresh = Settings()
        assert fresh.trusted_proxies == "10.0.0.1, 10.0.0.2"
        monkeypatch.setattr(settings, "trusted_proxies", fresh.trusted_proxies)
        req = _FakeRequest(host="10.0.0.1", xff="9.9.9.9, 10.0.0.1")
        assert get_client_ip(req) == "9.9.9.9"


class TestAuditForwardedIp:
    """Audit logs should record the X-Forwarded-For client behind a trusted proxy."""

    def test_login_audit_uses_forwarded_ip(self, client, db_session, monkeypatch):
        from app.models.user import User, UserRole
        from app.models.audit_log import AuditLog
        from app.auth.password import hash_password

        monkeypatch.setattr(settings, "trusted_proxies", ["testclient"])
        user = User(
            username="u1",
            password_hash=hash_password("pass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        client.post(
            "/auth/login",
            data={"username": "u1", "password": "pass"},
            headers={"X-Forwarded-For": "9.9.9.9"},
        )
        logs = db_session.query(AuditLog).filter(AuditLog.action == "LOGIN").all()
        assert logs
        assert logs[-1].ip_address == "9.9.9.9"

    def test_login_audit_ignores_forwarded_ip_when_untrusted(self, client, db_session):
        from app.models.user import User, UserRole
        from app.models.audit_log import AuditLog
        from app.auth.password import hash_password

        user = User(
            username="u1",
            password_hash=hash_password("pass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        client.post(
            "/auth/login",
            data={"username": "u1", "password": "pass"},
            headers={"X-Forwarded-For": "8.8.8.8"},
        )
        logs = db_session.query(AuditLog).filter(AuditLog.action == "LOGIN").all()
        assert logs
        assert logs[-1].ip_address == "testclient"