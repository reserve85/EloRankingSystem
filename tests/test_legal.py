"""Tests for legal pages (Impressum, Privacy) and cookie consent."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


TEST_DATABASE_URL = "sqlite:///./test_legal.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=test_engine)
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ── Impressum Page ────────────────────────────────────────────────────

class TestImpressumPage:
    """Tests for the Impressum page."""

    def test_impressum_accessible_without_auth(self, client, db_session):
        """Impressum page should be accessible without authentication."""
        resp = client.get("/ui/impressum")
        assert resp.status_code == 200
        assert "Impressum" in resp.text

    def test_impressum_contains_contact_company(self, client, db_session):
        """Impressum should render contact company from config."""
        resp = client.get("/ui/impressum")
        assert "Company" in resp.text

    def test_impressum_contains_contact_name(self, client, db_session):
        """Impressum should render contact name from config."""
        resp = client.get("/ui/impressum")
        assert "Max Mustermann" in resp.text

    def test_impressum_contains_contact_street(self, client, db_session):
        """Impressum should render contact street from config."""
        resp = client.get("/ui/impressum")
        assert "Musterstrasse 1" in resp.text

    def test_impressum_contains_contact_city(self, client, db_session):
        """Impressum should render contact city from config."""
        resp = client.get("/ui/impressum")
        assert "11111 Musterstadt" in resp.text

    def test_impressum_contains_contact_email(self, client, db_session):
        """Impressum should render contact email from config."""
        resp = client.get("/ui/impressum")
        assert "max.Mustermann@Muster.mu" in resp.text


# ── Privacy Policy Page ───────────────────────────────────────────────

class TestPrivacyPage:
    """Tests for the Privacy Policy page."""

    def test_privacy_accessible_without_auth(self, client, db_session):
        """Privacy Policy page should be accessible without authentication."""
        resp = client.get("/ui/privacy")
        assert resp.status_code == 200
        assert "Privacy Policy" in resp.text

    def test_privacy_contains_responsible_party(self, client, db_session):
        """Privacy Policy should contain responsible party section."""
        resp = client.get("/ui/privacy")
        assert "Responsible Party" in resp.text

    def test_privacy_contains_contact_data(self, client, db_session):
        """Privacy Policy should render contact data from config."""
        resp = client.get("/ui/privacy")
        assert "Max Mustermann" in resp.text
        assert "max.Mustermann@Muster.mu" in resp.text

    def test_privacy_contains_cookie_info(self, client, db_session):
        """Privacy Policy should contain cookie information."""
        resp = client.get("/ui/privacy")
        assert "Cookies" in resp.text

    def test_privacy_contains_gdpr_rights(self, client, db_session):
        """Privacy Policy should mention GDPR rights."""
        resp = client.get("/ui/privacy")
        assert "GDPR" in resp.text


# ── Cookie Consent Banner ────────────────────────────────────────────

class TestCookieConsent:
    """Tests for cookie consent banner functionality."""

    def test_cookie_consent_banner_in_base_template(self, client, db_session):
        """Cookie consent banner should be present in the base template."""
        resp = client.get("/ui/login")
        assert "cookie-consent-banner" in resp.text
        assert "acceptCookies" in resp.text
        assert "declineCookies" in resp.text

    def test_cookie_consent_has_accept_button(self, client, db_session):
        """Cookie consent banner should have Accept button."""
        resp = client.get("/ui/login")
        assert "Accept" in resp.text
        assert "acceptCookies()" in resp.text

    def test_cookie_consent_has_decline_button(self, client, db_session):
        """Cookie consent banner should have Decline button."""
        resp = client.get("/ui/login")
        assert "Decline" in resp.text
        assert "declineCookies()" in resp.text

    def test_cookie_consent_uses_localstorage(self, client, db_session):
        """Cookie consent should use localStorage for persistence."""
        resp = client.get("/ui/login")
        assert "localStorage.getItem('cookie_consent')" in resp.text
        assert "localStorage.setItem('cookie_consent'" in resp.text

    def test_cookie_consent_banner_initially_hidden(self, client, db_session):
        """Cookie consent banner should be initially hidden (shown via JS)."""
        resp = client.get("/ui/login")
        assert 'id="cookie-consent-banner"' in resp.text
        assert 'style="display:none' in resp.text


# ── Footer Links ─────────────────────────────────────────────────────

class TestFooterLinks:
    """Tests for legal page links in the footer."""

    def test_footer_has_impressum_link(self, client, db_session):
        """Footer should contain link to Impressum page."""
        resp = client.get("/ui/login")
        assert "/ui/impressum" in resp.text
        assert "Impressum" in resp.text

    def test_footer_has_privacy_link(self, client, db_session):
        """Footer should contain link to Privacy Policy page."""
        resp = client.get("/ui/privacy")
        assert "/ui/privacy" in resp.text
        assert "Privacy Policy" in resp.text
