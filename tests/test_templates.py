"""Tests for UI templates and page rendering."""

import pytest

from app.models.user import User, UserRole
from app.models.player import Player
from app.auth.password import hash_password


def _login_as(client, db_session, username, password, role):
    """Create a user and log in."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    client.post("/auth/login", data={"username": username, "password": password})
    return user


class TestLoginPage:
    """Tests for the login page."""

    def test_login_page_renders(self, client, db_session):
        """Login page should return 200 and contain login form."""
        resp = client.get("/ui/login")
        assert resp.status_code == 200
        assert "login-form" in resp.text
        assert "username" in resp.text
        assert "password" in resp.text

    def test_root_redirects_to_login(self, client, db_session):
        """Root URL should redirect to login page."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert "/ui/login" in resp.headers.get("location", "")


class TestDashboardPage:
    """Tests for the user dashboard page."""

    def test_dashboard_renders_for_user(self, client, db_session):
        """Dashboard should render for authenticated USER."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert resp.status_code == 200
        assert "Add Match" in resp.text
        assert "Ranking" in resp.text

    def test_dashboard_renders_for_admin(self, client, db_session):
        """Dashboard should render for authenticated ADMIN."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/dashboard")
        assert resp.status_code == 200
        assert "Add Match" in resp.text

    def test_dashboard_requires_auth(self, client, db_session):
        """Dashboard should redirect/401 when not authenticated."""
        resp = client.get("/ui/dashboard")
        assert resp.status_code == 401

    def test_dashboard_contains_navigation(self, client, db_session):
        """Dashboard should contain navigation links."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Dashboard" in resp.text

    def test_dashboard_user_no_admin_link(self, client, db_session):
        """USER role should not see Admin navigation link."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Admin</span>" not in resp.text or "/ui/admin" not in resp.text


class TestAdminPage:
    """Tests for the admin dashboard page."""

    def test_admin_page_renders_for_admin(self, client, db_session):
        """Admin page should render for ADMIN role."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert resp.status_code == 200
        assert "Admin Dashboard" in resp.text
        assert "Players" in resp.text
        assert "Users" in resp.text
        assert "Matches" in resp.text
        assert "Club Settings" in resp.text

    def test_admin_page_renders_for_system(self, client, db_session):
        """Admin page should render for SYSTEM role."""
        _login_as(client, db_session, "sys1", "pass", UserRole.SYSTEM)
        resp = client.get("/ui/admin")
        assert resp.status_code == 200

    def test_admin_page_blocked_for_user(self, client, db_session):
        """Admin page should be blocked for USER role (403)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/admin")
        assert resp.status_code == 403

    def test_admin_page_requires_auth(self, client, db_session):
        """Admin page should require authentication."""
        resp = client.get("/ui/admin")
        assert resp.status_code == 401

    def test_admin_contains_player_modal(self, client, db_session):
        """Admin page should contain player management modal."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "player-modal" in resp.text
        assert "player-name" in resp.text

    def test_admin_contains_user_modal(self, client, db_session):
        """Admin page should contain user management modal."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "user-modal" in resp.text
        assert "user-username" in resp.text

    def test_admin_contains_navigation(self, client, db_session):
        """Admin page should contain both Dashboard and Admin nav links."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "/ui/dashboard" in resp.text
        assert "/ui/admin" in resp.text


class TestUserManagementAPI:
    """Tests for user management API endpoints used by admin page."""

    def test_admin_can_list_users(self, client, db_session):
        """ADMIN should be able to list users."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/users/")
        assert resp.status_code == 200
        users = resp.json()
        assert len(users) >= 1

    def test_admin_can_create_user(self, client, db_session):
        """ADMIN should be able to create a new user."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.post("/users/", json={
            "username": "newuser", "password": "pass123", "role": "USER"
        })
        assert resp.status_code == 201
        assert resp.json()["username"] == "newuser"
        assert resp.json()["role"] == "USER"

    def test_admin_cannot_create_system_user(self, client, db_session):
        """ADMIN should not be able to create SYSTEM users."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.post("/users/", json={
            "username": "hacker", "password": "pass", "role": "SYSTEM"
        })
        assert resp.status_code == 400

    def test_user_cannot_list_users(self, client, db_session):
        """USER should not be able to list users."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/users/")
        assert resp.status_code == 403

    def test_admin_can_update_user(self, client, db_session):
        """ADMIN should be able to update a user's role."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        # Create user first
        create_resp = client.post("/users/", json={
            "username": "updatee", "password": "pass", "role": "USER"
        })
        user_id = create_resp.json()["id"]

        resp = client.put(f"/users/{user_id}", json={"role": "ADMIN"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "ADMIN"

    def test_system_user_cannot_be_downgraded(self, client, db_session):
        """SYSTEM user role cannot be changed via API."""
        sys_user = _login_as(client, db_session, "sys1", "pass", UserRole.SYSTEM)
        resp = client.put(f"/users/{sys_user.id}", json={"role": "USER"})
        assert resp.status_code == 400

    def test_system_user_cannot_be_disabled(self, client, db_session):
        """SYSTEM user cannot be disabled via API."""
        sys_user = _login_as(client, db_session, "sys1", "pass", UserRole.SYSTEM)
        resp = client.put(f"/users/{sys_user.id}", json={"active": False})
        assert resp.status_code == 400


class TestSettingsAPI:
    """Tests for club settings API endpoints."""

    def test_admin_can_get_settings(self, client, db_session):
        """ADMIN should be able to get club settings."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/settings/")
        assert resp.status_code == 200
        data = resp.json()
        assert "club_name" in data
        assert "default_elo" in data
        assert "k_factor" in data
        assert "inactivity_months" in data

    def test_admin_can_update_settings(self, client, db_session):
        """ADMIN should be able to update club settings."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.put("/settings/", json={
            "club_name": "New Club Name",
            "default_elo": 1500,
            "k_factor": 24,
            "inactivity_months": 6,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["club_name"] == "New Club Name"
        assert data["default_elo"] == 1500

    def test_user_cannot_get_settings(self, client, db_session):
        """USER should not be able to access settings."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/settings/")
        assert resp.status_code == 403

    def test_unauthenticated_cannot_get_settings(self, client, db_session):
        """Unauthenticated request should be rejected."""
        resp = client.get("/settings/")
        assert resp.status_code == 401


class TestTablerUIAssets:
    """Tests that Tabler UI CSS/JS assets are referenced."""

    def test_login_page_has_tabler_css(self, client, db_session):
        """Login page should reference Tabler CSS."""
        resp = client.get("/ui/login")
        assert "tabler.min.css" in resp.text

    def test_login_page_has_tabler_js(self, client, db_session):
        """Login page should reference Tabler JS."""
        resp = client.get("/ui/login")
        assert "tabler.min.js" in resp.text

    def test_dashboard_has_datatables(self, client, db_session):
        """Dashboard should reference DataTables."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "datatables" in resp.text.lower()

    def test_responsive_viewport_meta(self, client, db_session):
        """Login page should have responsive viewport meta tag."""
        resp = client.get("/ui/login")
        assert "viewport" in resp.text
        assert "width=device-width" in resp.text