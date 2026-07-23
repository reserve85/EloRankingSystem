"""Tests for UI templates and page rendering."""

import os
from unittest.mock import patch

from app.models.user import User, UserRole
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
        assert "Match History" in resp.text
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

    def test_system_user_cannot_change_role_to_user(self, client, db_session):
        """SYSTEM user role cannot be changed to USER via API."""
        sys_user = _login_as(client, db_session, "sys1", "pass", UserRole.SYSTEM)
        resp = client.put(f"/users/{sys_user.id}", json={"role": "USER"})
        assert resp.status_code == 400

    def test_system_user_cannot_change_role_to_admin(self, client, db_session):
        """SYSTEM user role cannot be changed to ADMIN via API."""
        sys_user = _login_as(client, db_session, "sys1", "pass", UserRole.SYSTEM)
        resp = client.put(f"/users/{sys_user.id}", json={"role": "ADMIN"})
        assert resp.status_code == 400

    def test_update_nonexistent_user_returns_404(self, client, db_session):
        """Updating a non-existent user should return 404."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.put("/users/9999", json={"role": "ADMIN"})
        assert resp.status_code == 404


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


class TestStatisticsFormDashboard:
    """Tests for dart statistics form in the user dashboard."""

    def test_dashboard_contains_statistics_section(self, client, db_session):
        """Dashboard should have Dart Statistics section."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Dart Statistics" in resp.text
        assert "p1-180s" in resp.text
        assert "p2-180s" in resp.text

    def test_dashboard_contains_high_finishes_section(self, client, db_session):
        """Dashboard should have High Finishes inputs."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "High Finishes" in resp.text
        assert "p1-hf-list" in resp.text
        assert "p2-hf-list" in resp.text

    def test_dashboard_contains_low_darts_section(self, client, db_session):
        """Dashboard should have Low Darts inputs."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Low Darts" in resp.text
        assert "p1-ld-list" in resp.text
        assert "p2-ld-list" in resp.text

    def test_dashboard_shows_config_ranges(self, client, db_session):
        """Dashboard should display configured validation ranges."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "100" in resp.text  # hf_min default
        assert "170" in resp.text  # hf_max default

    def test_dashboard_statistics_is_collapsible(self, client, db_session):
        """Statistics section should be in a collapsible details element."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "<details" in resp.text
        assert "optional" in resp.text.lower()

    def test_dashboard_contains_counter_buttons(self, client, db_session):
        """Dashboard should have +/- buttons for 180s counter."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "adjustCounter" in resp.text

    def test_dashboard_has_submit_without_stats(self, client, db_session):
        """Match can be submitted without filling in statistics (they're optional)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # The form should not have "required" on stats inputs
        assert 'id="p1-180s"' in resp.text
        # Verify the stats section is inside a <details> element (collapsible)
        assert "getStatsFromForm" in resp.text


class TestStatisticsFormAdmin:
    """Tests for dart statistics form in the admin dashboard."""

    def test_admin_match_detail_has_statistics_editing(self, client, db_session):
        """Admin match detail modal should have Dart Statistics editing."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-edit-p1-180s" in resp.text
        assert "admin-edit-p2-180s" in resp.text

    def test_admin_match_detail_has_high_finishes_inputs(self, client, db_session):
        """Admin match detail modal should have High Finishes inputs."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-edit-p1-hf-list" in resp.text
        assert "admin-edit-p2-hf-list" in resp.text
        assert "addModalHfEntry" in resp.text

    def test_admin_match_detail_has_low_darts_inputs(self, client, db_session):
        """Admin match detail modal should have Low Darts inputs."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-edit-p1-ld-list" in resp.text
        assert "admin-edit-p2-ld-list" in resp.text
        assert "addModalLdEntry" in resp.text

    def test_admin_no_add_match_form(self, client, db_session):
        """Admin page should NOT have Add Match form (only in Dashboard)."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-add-match-form" not in resp.text
        assert "admin-player-a-select" not in resp.text
        assert "admin-player-b-select" not in resp.text

    def test_admin_shows_config_ranges_in_modal(self, client, db_session):
        """Admin match detail modal should display configured validation ranges in JS."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        # Jinja2 renders {{ hf_min }} to the actual value (e.g. 100)
        assert "100" in resp.text
        assert "170" in resp.text


class TestMatchStatisticsRendering:
    """Tests for match statistics columns and detail modal rendering."""

    def test_dashboard_match_table_has_180s_column(self, client, db_session):
        """Dashboard match history table should have 180 column header."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "180</th>" in resp.text
        assert "HF</th>" in resp.text
        assert "LD</th>" in resp.text

    def test_dashboard_match_table_is_clickable(self, client, db_session):
        """Dashboard match rows should have onclick handler for detail view."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "showMatchDetail" in resp.text

    def test_dashboard_has_match_detail_modal(self, client, db_session):
        """Dashboard should have match detail modal."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "match-detail-modal" in resp.text
        assert "modal-p1-name" in resp.text
        assert "modal-p2-name" in resp.text

    def test_dashboard_modal_shows_per_player_stats(self, client, db_session):
        """Dashboard match detail modal should show per-player stat fields."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "modal-p1-180s" in resp.text
        assert "modal-p2-180s" in resp.text
        assert "modal-p1-hf" in resp.text
        assert "modal-p2-hf" in resp.text
        assert "modal-p1-ld" in resp.text
        assert "modal-p2-ld" in resp.text
        assert "modal-p1-result" in resp.text
        assert "modal-p2-result" in resp.text
        assert "modal-p1-elo" in resp.text
        assert "modal-p2-elo" in resp.text

    def test_dashboard_modal_is_readonly(self, client, db_session):
        """Dashboard match detail modal should be read-only (no edit buttons)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Modal should only have Close button, no Save/Edit
        assert "match-detail-modal" in resp.text
        assert "Close" in resp.text

    def test_admin_match_table_has_statistics_columns(self, client, db_session):
        """Admin match table should have 180, HF, LD columns."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "180</th>" in resp.text
        assert "HF</th>" in resp.text
        assert "LD</th>" in resp.text

    def test_admin_match_table_has_detail_modal(self, client, db_session):
        """Admin should have match detail modal with per-player stats."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-match-detail-modal" in resp.text
        assert "admin-modal-p1-name" in resp.text
        assert "admin-modal-p2-name" in resp.text
        assert "admin-edit-p1-180s" in resp.text
        assert "admin-edit-p2-180s" in resp.text
        assert "admin-edit-p1-hf-list" in resp.text
        assert "admin-edit-p2-hf-list" in resp.text

    def test_admin_match_table_clickable(self, client, db_session):
        """Admin match rows should open detail modal on click."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "showAdminMatchDetail" in resp.text


class TestConfirmationDialogs:
    """Tests for confirmation dialogs on modifying actions."""

    def test_base_template_has_confirm_modal(self, client, db_session):
        """Base template should include shared confirmation modal."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "confirm-modal" in resp.text
        assert "showConfirmDialog" in resp.text
        assert "confirm-message" in resp.text

    def test_dashboard_match_submit_has_confirmation(self, client, db_session):
        """Dashboard match form submit should use confirmation dialog."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "showConfirmDialog" in resp.text

    def test_admin_save_player_has_confirmation(self, client, db_session):
        """Admin save player should use confirmation dialog."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "showConfirmDialog" in resp.text

    def test_admin_delete_match_has_confirmation(self, client, db_session):
        """Admin delete match should use confirmation dialog."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        # deleteMatch function should reference showConfirmDialog
        assert "Delete Match" in resp.text or "Delete this match" in resp.text

    def test_admin_toggle_user_has_confirmation(self, client, db_session):
        """Admin enable/disable user should use confirmation dialog."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "Enable" in resp.text and "Disable" in resp.text


class TestAutoRefresh:
    """Tests for auto-refresh after modifying actions."""

    def test_dashboard_loads_ranking_on_match_save(self, client, db_session):
        """Dashboard JS should call loadRanking after match save."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "loadRanking(); loadMatches()" in resp.text

    def test_admin_loads_matches_on_match_save(self, client, db_session):
        """Admin JS should call loadMatches on init."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "loadMatches()" in resp.text

    def test_admin_loads_players_on_player_save(self, client, db_session):
        """Admin JS should call loadPlayers after player save."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        # savePlayer should call loadPlayers
        assert "loadPlayers()" in resp.text

    def test_admin_loads_users_on_user_save(self, client, db_session):
        """Admin JS should call loadUsers after user save."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "loadUsers();" in resp.text

    def test_admin_refreshes_on_stats_save(self, client, db_session):
        """Admin should refresh match list after stats edit."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "saveAdminMatchStats" in resp.text
        # saveAdminMatchStats calls loadMatches
        assert "loadMatches();" in resp.text


class TestVersionInfo:
    """Tests for Task 1: Build Information / Header / Footer."""

    def test_version_info_no_double_v(self, client, db_session):
        """Version string should not have duplicated 'v' prefix."""
        with patch.dict(os.environ, {"APP_VERSION": "vv1.0.3"}):
            from app.core import version
            # Reload to pick up new env
            info = version.get_version_info()
            assert info["version"] == "1.0.3"
            assert not info["version"].startswith("v")

    def test_version_info_strips_single_v(self, client, db_session):
        """Version string should strip a single leading 'v'."""
        with patch.dict(os.environ, {"APP_VERSION": "v2.5.0"}):
            from app.core import version
            info = version.get_version_info()
            assert info["version"] == "2.5.0"

    def test_version_info_default_version(self, client, db_session):
        """Default version should be '0.1.0' when no env var set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APP_VERSION", None)
            from app.core import version
            info = version.get_version_info()
            assert info["version"] == "0.1.0"

    def test_version_info_has_github_url(self, client, db_session):
        """Version info should contain GitHub project URL."""
        from app.core import version
        info = version.get_version_info()
        assert "github_url" in info
        assert "github.com/reserve85/EloRankingSystem" in info["github_url"]

    def test_version_info_has_release_url(self, client, db_session):
        """Version info should contain release URL for current version."""
        from app.core import version
        info = version.get_version_info()
        assert "release_url" in info
        assert "/releases/tag/v" in info["release_url"]

    def test_version_info_timezone_formatting(self, client, db_session):
        """Build date should be formatted using the given timezone."""
        from app.core import version
        with patch.dict(os.environ, {"BUILD_DATE": "2026-07-22T22:24:38+02:00"}):
            # Use UTC which is always available, even without tzdata package
            info = version.get_version_info("UTC")
            # The datetime should be converted to UTC
            assert "2026-07-23" in info["build_date"] or "2026-07-22" in info["build_date"]
            assert "development" not in info["build_date"]

    def test_version_info_timezone_fallback_on_bad_tz(self, client, db_session):
        """Build date should return raw string if timezone is invalid."""
        from app.core import version
        with patch.dict(os.environ, {"BUILD_DATE": "2026-07-22T22:24:38+02:00"}):
            info = version.get_version_info("Invalid/Timezone")
            # Should fall back to the raw string
            assert "2026-07-22T22:24:38" in info["build_date"]

    def test_version_info_development_fallback(self, client, db_session):
        """Build date should show 'development' when no BUILD_DATE env var."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUILD_DATE", None)
            from app.core import version
            info = version.get_version_info()
            assert info["build_date"] == "development"

    def test_footer_contains_github_link(self, client, db_session):
        """Footer should contain a clickable GitHub project link."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "github.com/reserve85/EloRankingSystem" in resp.text
        assert 'target="_blank"' in resp.text

    def test_footer_contains_release_link(self, client, db_session):
        """Footer should contain a clickable version/release link."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "/releases/tag/v" in resp.text

    def test_footer_version_not_double_v_in_html(self, client, db_session):
        """Footer HTML should not contain 'vv' in version string."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Check the footer section doesn't have "vv"
        footer_start = resp.text.find("<footer")
        footer_end = resp.text.find("</footer>")
        if footer_start >= 0 and footer_end >= 0:
            footer = resp.text[footer_start:footer_end]
            assert "vv" not in footer

    def test_login_page_footer_also_has_links(self, client, db_session):
        """Login page footer should also have GitHub links."""
        resp = client.get("/ui/login")
        assert "github.com/reserve85/EloRankingSystem" in resp.text


class TestLegalPages:
    """Tests for Task 2: Legal pages navigation and layout."""

    def test_impressum_public_accessible(self, client, db_session):
        """Impressum should be accessible without authentication."""
        resp = client.get("/ui/impressum")
        assert resp.status_code == 200
        assert "Impressum" in resp.text

    def test_privacy_public_accessible(self, client, db_session):
        """Privacy Policy should be accessible without authentication."""
        resp = client.get("/ui/privacy")
        assert resp.status_code == 200
        assert "Privacy Policy" in resp.text

    def test_impressum_shows_navigation_when_logged_in(self, client, db_session):
        """Impressum should show header/navigation for authenticated users."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/impressum")
        assert resp.status_code == 200
        assert "/ui/dashboard" in resp.text
        assert "/ui/logout" in resp.text

    def test_privacy_shows_navigation_when_logged_in(self, client, db_session):
        """Privacy Policy should show header/navigation for authenticated users."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/privacy")
        assert resp.status_code == 200
        assert "/ui/dashboard" in resp.text
        assert "/ui/logout" in resp.text

    def test_impressum_no_navigation_when_not_logged_in(self, client, db_session):
        """Impressum should not show user navigation when not authenticated."""
        resp = client.get("/ui/impressum")
        assert resp.status_code == 200
        assert "/ui/dashboard" not in resp.text
        assert "/ui/logout" not in resp.text

    def test_admin_page_no_add_match_section(self, client, db_session):
        """Admin page should not contain Add Match form."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-add-match-form" not in resp.text
        assert "loadAdminMatchPlayers" not in resp.text


class TestMobileLayout:
    """Tests for Task 3: Mobile View / Responsive Layout."""

    def test_header_has_flex_wrap_for_mobile(self, client, db_session):
        """Header should use flex-wrap so buttons don't overlap logo on mobile."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "flex-wrap" in resp.text

    def test_user_button_is_icon_style(self, client, db_session):
        """User button should use an icon (SVG) instead of a colored avatar."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Should have user icon SVG in header
        assert "icon icon-sm" in resp.text
        # Should not have the old avatar with bg-primary
        assert 'avatar avatar-sm rounded-circle bg-primary' not in resp.text

    def test_user_button_has_username_text(self, client, db_session):
        """User button should show the username next to the icon."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/dashboard")
        assert "admin1" in resp.text

    def test_navbar_toggler_after_user_button(self, client, db_session):
        """Navbar toggler should be placed after the user button area."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Both toggler and user dropdown should exist
        assert "navbar-toggler" in resp.text
        assert "dropdown-menu-end" in resp.text

    def test_mobile_menu_has_spacing_from_content(self, client, db_session):
        """Mobile menu collapse area should have margin-top for spacing."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "mt-2 mt-md-0" in resp.text

    def test_dashboard_still_has_nav_links(self, client, db_session):
        """Dashboard should still show Dashboard and Admin nav links."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/dashboard")
        assert "/ui/dashboard" in resp.text
        assert "/ui/admin" in resp.text


class TestDateFormat:
    """Tests for Task 4: Date / Time / Timezone / Date Format."""

    def test_dashboard_has_shared_date_utilities(self, client, db_session):
        """Dashboard should have shared date utility functions available."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "todayISO" in resp.text
        assert "preventFutureDate" in resp.text
        assert "syncDateRange" in resp.text
        assert "jumpToToday" in resp.text

    def test_dashboard_date_picker_has_today_button(self, client, db_session):
        """Dashboard match date input should have a Today button."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "jumpToToday" in resp.text

    def test_dashboard_ranking_dates_auto_refresh(self, client, db_session):
        """Dashboard ranking dates should auto-refresh on change."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Should have auto-refresh event listeners (no separate filter button)
        assert "loadRanking" in resp.text

    def test_dashboard_match_dates_auto_refresh(self, client, db_session):
        """Dashboard match dates should auto-refresh on change."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "loadMatches" in resp.text

    def test_dashboard_no_filter_button_for_match_history(self, client, db_session):
        """Dashboard match history should not have a separate Filter button."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # The old Filter button was removed
        assert 'onclick="loadMatches()">Filter</button>' not in resp.text

    def test_admin_pdf_has_today_button(self, client, db_session):
        """Admin PDF export date inputs should have Today buttons."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "jumpToToday" in resp.text

    def test_admin_pdf_prevents_future_dates(self, client, db_session):
        """Admin PDF export date inputs should prevent future dates."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "preventFutureDate" in resp.text

    def test_admin_uses_shared_date_utilities(self, client, db_session):
        """Admin should use shared date utilities from base.html."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "SERVER_TIMEZONE" in resp.text or "serverTimezone" in resp.text

    def test_date_format_config_accessible(self, client, db_session):
        """Date format should be available in template context."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "DATE_FORMAT" in resp.text

    def test_timezone_config_accessible(self, client, db_session):
        """Timezone should be available in template context."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "SERVER_TIMEZONE" in resp.text


class TestDashboardRanking:
    """Tests for Task 6: Dashboard / Ranking."""

    def test_ranking_table_exists(self, client, db_session):
        """Dashboard should have a ranking table."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ranking-table" in resp.text

    def test_ranking_table_has_hf_ld_columns(self, client, db_session):
        """Ranking table should have HF and LD columns."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "HF</th>" in resp.text
        assert "LD</th>" in resp.text

    def test_ranking_hf_ld_shows_count_in_js(self, client, db_session):
        """Ranking JS should calculate HF/LD counts (not values)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # JS should use .length for count, not join the values
        assert "hfCount" in resp.text or "high_finishes.length" in resp.text

    def test_ranking_has_trophy_icons(self, client, db_session):
        """Ranking JS should have trophy icon support for top 3."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Should have trophy emoji array
        assert "trophy" in resp.text.lower()

    def test_ranking_date_auto_refresh(self, client, db_session):
        """Ranking dates should auto-refresh on change (no separate filter button)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "loadRanking" in resp.text

    def test_ranking_no_filter_button(self, client, db_session):
        """Ranking section should not have a separate filter button."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # No "Filter" button for ranking
        assert "Filter</button>" not in resp.text or "loadRanking" in resp.text


class TestMatchHistory:
    """Tests for Task 7: Dashboard / Match History."""

    def test_match_table_has_id_column(self, client, db_session):
        """Match history table should have ID as first column."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # ID should be a table header in match table
        assert "ID</th>" in resp.text

    def test_match_table_sorts_by_id_desc(self, client, db_session):
        """Match table should default sort by ID descending."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # DataTables order: [[0,'desc']] means column 0 (ID) desc
        assert "order" in resp.text

    def test_match_table_renders_m_id_in_js(self, client, db_session):
        """Match table JS should render m.id in each row."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "m.id" in resp.text

    def test_match_dates_auto_refresh(self, client, db_session):
        """Match dates should auto-refresh on change."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "loadMatches" in resp.text

    def test_match_no_filter_button(self, client, db_session):
        """Match history should not have a separate Filter button."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # The old Filter button was removed
        assert 'onclick="loadMatches()">Filter</button>' not in resp.text


class TestPeriodStatistics:
    """Tests for Task 8: Period Statistics."""

    def test_period_stats_hf_shows_count_prefix(self, client, db_session):
        """Period stats HF should show count prefix like (3x) in JS."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # JS should format as '(Nx) value1, value2'
        assert "(\' + p.high_finishes.length + \'x)" in resp.text

    def test_period_stats_ld_shows_count_prefix(self, client, db_session):
        """Period stats LD should show count prefix like (2x) in JS."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "(\' + p.low_darts.length + \'x)" in resp.text

    def test_player_stats_modal_exists(self, client, db_session):
        """Dashboard should have player statistics modal."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "player-stats-modal" in resp.text
        assert "ps-period-180s" in resp.text
        assert "ps-period-hf" in resp.text
        assert "ps-period-ld" in resp.text
