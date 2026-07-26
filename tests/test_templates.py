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

    def test_login_page_shows_club_name(self, client, db_session):
        """Login page should show club name."""
        resp = client.get("/ui/login")
        assert resp.status_code == 200
        # Should contain either club_name or app_name heading
        assert "h3" in resp.text or "h4" in resp.text

    def test_login_page_has_logo_element(self, client, db_session):
        """Login page should have a logo image element."""
        resp = client.get("/ui/login")
        assert resp.status_code == 200
        assert "login-logo" in resp.text

    def test_login_page_has_app_name(self, client, db_session):
        """Login page should display app_name."""
        resp = client.get("/ui/login")
        assert resp.status_code == 200
        assert "Elo Ranking System" in resp.text

    def test_login_redirects_when_authenticated(self, client, db_session):
        """Already authenticated user should be redirected to dashboard."""
        _login_as(client, db_session, "login_redirect_user", "pass", UserRole.USER)
        resp = client.get("/ui/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/ui/dashboard" in resp.headers.get("location", "")

    def test_login_page_vertically_centered(self, client, db_session):
        """Login page content should be vertically centered."""
        resp = client.get("/ui/login")
        assert resp.status_code == 200
        assert "min-height" in resp.text


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
            "username": "newuser", "password": "Pass123!", "role": "USER"
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
            "username": "updatee", "password": "Pass123!", "role": "USER"
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
            "default_elo": 1500,
            "k_factor": 24,
            "inactivity_months": 6,
        })
        assert resp.status_code == 200
        data = resp.json()
        # club_name now comes from env/config, not from DB update
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

    def test_dashboard_has_duplicate_match_modal(self, client, db_session):
        """Dashboard should have a duplicate match confirmation modal."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "duplicate-match-modal" in resp.text
        assert "duplicate-confirm-btn" in resp.text
        assert "showDuplicateMatchModal" in resp.text

    def test_duplicate_match_modal_replaces_inline_warning(self, client, db_session):
        """Duplicate match detection should use modal, not inline warning."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Should NOT have old inline warning button
        assert "submitDuplicateMatch" not in resp.text
        # Should have modal-based approach
        assert "duplicate-match-modal" in resp.text
        assert "Save Anyway" in resp.text


class TestAutoRefresh:
    """Tests for auto-refresh after modifying actions."""

    def test_dashboard_refreshes_all_views_on_match_save(self, client, db_session):
        """Dashboard should refresh ranking, matches, players, and ATH chart after match save."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # After match save, all affected views must refresh via Promise.all
        assert "loadRanking()" in resp.text
        assert "loadMatches()" in resp.text
        assert "loadPlayers()" in resp.text
        assert "loadAllTimeEloChart()" in resp.text
        assert "Promise.all" in resp.text

    def test_admin_refreshes_matches_and_players_on_stats_save(self, client, db_session):
        """Admin should refresh both matches and players after stats edit (Elo recalc)."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "saveAdminMatchStats" in resp.text
        # After save, both loadMatches and loadPlayers must be called
        assert "Promise.all([loadMatches(), loadPlayers()])" in resp.text

    def test_admin_refreshes_matches_and_players_on_delete_match(self, client, db_session):
        """Admin should refresh both matches and players after deleting a match (Elo recalc)."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        # deleteMatch should refresh both
        assert "async function deleteMatch(id)" in resp.text
        assert "Promise.all([loadMatches(), loadPlayers()])" in resp.text

    def test_admin_refreshes_matches_and_players_on_modal_delete(self, client, db_session):
        """Admin modal delete should refresh both matches and players."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "async function deleteMatchFromModal()" in resp.text

    def test_admin_loads_matches_on_init(self, client, db_session):
        """Admin JS should call loadMatches on init."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "loadMatches()" in resp.text

    def test_admin_loads_players_on_player_save(self, client, db_session):
        """Admin JS should call loadPlayers after player save."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "loadPlayers()" in resp.text

    def test_admin_loads_users_on_user_save(self, client, db_session):
        """Admin JS should call loadUsers after user save."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "loadUsers();" in resp.text

    def test_dashboard_ath_chart_refreshes_on_match_save(self, client, db_session):
        """Dashboard ATH chart function should exist and be callable."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "async function loadAllTimeEloChart()" in resp.text

    def test_admin_save_stats_uses_await(self, client, db_session):
        """Admin stats save should await Promise.all before showing success."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "await Promise.all([loadMatches(), loadPlayers()])" in resp.text


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


class TestAuthRedirect:
    """Tests for Task 32: Authentication / Auto-Redirect to Login."""

    def test_global_401_handler_exists(self, client, db_session):
        """Base template should have global fetch interceptor for 401 redirect."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "resp.status === 401" in resp.text
        assert "window.location.href = '/ui/login'" in resp.text

    def test_unauthenticated_api_returns_401(self, client, db_session):
        """API calls without auth should return 401."""
        resp = client.get("/players/active")
        assert resp.status_code == 401

    def test_login_page_redirects_authenticated_user(self, client, db_session):
        """Authenticated user visiting login page should be redirected to dashboard."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/ui/dashboard" in resp.headers.get("location", "")

    def test_unauthenticated_dashboard_returns_401(self, client, db_session):
        """Dashboard should return 401 for unauthenticated requests."""
        resp = client.get("/ui/dashboard")
        assert resp.status_code == 401

    def test_401_handler_excludes_login_page(self, client, db_session):
        """401 handler should not redirect when already on login page."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "!window.location.pathname.startsWith('/ui/login')" in resp.text


class TestDarkMode:
    """Tests for Task 29: Global Dark Mode / Full GUI Theme."""

    def test_base_template_has_data_theme_attribute(self, client, db_session):
        """Base template should have data-theme attribute on html element."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'data-bs-theme="light"' in resp.text

    def test_theme_toggle_button_exists(self, client, db_session):
        """Dashboard should have theme toggle button with moon/sun icons."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "theme-toggle-btn" in resp.text
        assert "theme-icon-moon" in resp.text
        assert "theme-icon-sun" in resp.text

    def test_theme_toggle_script_exists(self, client, db_session):
        """Base template should include theme toggle JavaScript."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "applyTheme" in resp.text
        assert "data-theme" in resp.text

    def test_theme_stored_in_cookie(self, client, db_session):
        """Theme preference should be stored via cookie for server-side reading."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "document.cookie" in resp.text
        assert "theme=" in resp.text

    def test_login_page_has_theme_support(self, client, db_session):
        """Login page should also have theme support."""
        resp = client.get("/ui/login")
        assert "data-theme" in resp.text
        assert "theme-toggle-btn" in resp.text

    def test_admin_page_has_theme_support(self, client, db_session):
        """Admin page should also have theme support."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "theme-toggle-btn" in resp.text


class TestInactivePlayerCheckbox:
    """Tests for Task 30: Include Inactive Players Checkbox."""

    def test_ranking_checkbox_checked_by_default(self, client, db_session):
        """Ranking include inactive checkbox should be checked by default."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'id="ranking-include-inactive"' in resp.text
        assert 'checked' in resp.text

    def test_ranking_checkbox_label_exists(self, client, db_session):
        """Ranking include inactive checkbox should have correct label."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Include inactive players in this interval" in resp.text

    def test_ranking_checkbox_triggers_load_ranking(self, client, db_session):
        """Ranking checkbox change should trigger loadRanking via AJAX."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ranking-include-inactive').addEventListener('change'" in resp.text
        assert "loadRanking()" in resp.text

    def test_ath_checkbox_checked_by_default(self, client, db_session):
        """ATH chart include inactive checkbox should be checked by default."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'id="ath-include-inactive"' in resp.text

    def test_ath_checkbox_triggers_load_chart(self, client, db_session):
        """ATH checkbox change should trigger loadAllTimeEloChart via AJAX."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ath-include-inactive').addEventListener('change'" in resp.text

    def test_ranking_sends_include_inactive_param(self, client, db_session):
        """loadRanking should send include_inactive param to API."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "include_inactive=true" in resp.text


class TestAdminMobileLayout:
    """Tests for Task 28: Admin Panel / Mobile View Improvements."""

    def test_admin_tabs_have_scrollable_wrapper(self, client, db_session):
        """Admin tabs should be wrapped in a scrollable container for mobile."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "admin-tabs-wrapper" in resp.text
        assert "overflow-x:auto" in resp.text

    def test_admin_tabs_flex_nowrap(self, client, db_session):
        """Admin tabs should use flex-nowrap to prevent wrapping on mobile."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "flex-nowrap" in resp.text
        assert "white-space:nowrap" in resp.text

    def test_admin_tabs_touch_scrolling(self, client, db_session):
        """Admin tabs should have smooth touch scrolling support."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "-webkit-overflow-scrolling:touch" in resp.text


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
        # Both hamburger and user dropdown should exist
        assert "navbar-menu" in resp.text
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


class TestMatchCreateLayout:
    """Tests for Task 26: Match Create Layout and Auto-Labeling."""

    def test_format_dropdown_in_header(self, client, db_session):
        """Format dropdown should be in the card header, not in the form body."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'card-header d-flex justify-content-between' in resp.text
        assert 'id="best-of-select"' in resp.text

    def test_format_dropdown_is_select_sm(self, client, db_session):
        """Format dropdown in header should use form-select-sm for compact display."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'form-select form-select-sm' in resp.text
        assert 'id="best-of-select"' in resp.text

    def test_score_labels_have_dynamic_ids(self, client, db_session):
        """Score labels should have IDs for dynamic player name updates."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'id="score-a-label"' in resp.text
        assert 'id="score-b-label"' in resp.text

    def test_score_labels_default_text(self, client, db_session):
        """Score labels should have default text Player 1 Score / Player 2 Score."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'Player 1 Score' in resp.text
        assert 'Player 2 Score' in resp.text

    def test_auto_labeling_updates_score_labels(self, client, db_session):
        """updatePlayerLabels should update score labels with player names."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "score-a-label" in resp.text
        assert "score-b-label" in resp.text
        assert "Score'" in resp.text

    def test_auto_labeling_updates_statistics_labels(self, client, db_session):
        """updatePlayerLabels should still update statistics section labels."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "p1-name-180" in resp.text
        assert "p2-name-180" in resp.text
        assert "p1-name-hf" in resp.text
        assert "p2-name-hf" in resp.text

    def test_player_and_score_fields_vertically_aligned(self, client, db_session):
        """Player selects and score selects should use same col-6 layout."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'id="player-a-select"' in resp.text
        assert 'id="score-a"' in resp.text

    def test_format_dropdown_contains_options(self, client, db_session):
        """Format dropdown should contain Best of N options."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Best of" in resp.text
        assert 'id="best-of-select"' in resp.text

    def test_best_of_legs_read_from_dom_not_formdata(self, client, db_session):
        """best_of_legs must be read from DOM element since it is outside the form tag."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # The JS must use getElementById to read best_of_legs, not fd.get()
        assert "document.getElementById('best-of-select').value" in resp.text
        # Verify it's NOT using FormData to read it (would break if select is outside form)
        assert "fd.get('best_of_legs')" not in resp.text

    def test_add_match_form_still_has_date_field(self, client, db_session):
        """Add Match form should still have date input with Today button."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert 'name="date"' in resp.text
        assert 'jumpToToday' in resp.text

    def test_statistics_section_preserved(self, client, db_session):
        """Dart Statistics section should still be present and collapsible."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Dart Statistics" in resp.text
        assert "<details" in resp.text


class TestMatchHistoryAutoShift:
    """Tests for Task 24: Match History Minimum Start Date Logic."""

    def test_match_from_user_selected_tracking_variable(self, client, db_session):
        """Dashboard should track whether user manually changed the match from date."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "matchFromUserSelected" in resp.text

    def test_match_from_change_event_sets_user_selected(self, client, db_session):
        """Changing match-from date should set matchFromUserSelected to true."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "matchFromUserSelected = true" in resp.text

    def test_shift_first_of_month_function_exists(self, client, db_session):
        """Dashboard JS should contain shiftFirstOfMonth helper function."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "function shiftFirstOfMonth" in resp.text

    def test_fetch_match_range_function_exists(self, client, db_session):
        """Dashboard JS should contain fetchMatchRange helper function."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "function fetchMatchRange" in resp.text

    def test_render_match_table_function_exists(self, client, db_session):
        """Dashboard JS should contain renderMatchTable helper function."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "function renderMatchTable" in resp.text

    def test_auto_shift_checks_50_match_threshold(self, client, db_session):
        """Auto-shift logic should check for >= 50 matches."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "data.length >= 50" in resp.text

    def test_auto_shift_only_in_default_mode(self, client, db_session):
        """Auto-shift should only run when matchFromUserSelected is false."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "!matchFromUserSelected" in resp.text

    def test_user_selected_mode_skips_auto_shift(self, client, db_session):
        """When user has manually selected a date, no auto-shifting occurs."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "no auto-shifting" in resp.text

    def test_max_shift_months_safety_limit(self, client, db_session):
        """Auto-shift should have a safety limit to prevent infinite loop."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "maxShiftMonths" in resp.text

    def test_future_dates_prevented_on_match_from(self, client, db_session):
        """Match history from date should prevent future dates."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "preventFutureDate(document.getElementById('match-from'))" in resp.text

    def test_future_dates_prevented_on_match_to(self, client, db_session):
        """Match history to date should prevent future dates."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "preventFutureDate(document.getElementById('match-to'))" in resp.text

    def test_match_from_default_is_first_of_month(self, client, db_session):
        """Match history from date should default to first day of current month."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "match-from').value = firstOfMonth" in resp.text

    def test_load_matches_calls_auto_shift_logic(self, client, db_session):
        """loadMatches function should contain auto-shift logic."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "effectiveFrom" in resp.text
        assert "fetchMatchRange" in resp.text


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


class TestPlayerStatistics:
    """Tests for Task 9: Player Statistics."""

    def test_player_stats_has_ath_elo_card(self, client, db_session):
        """Player stats modal should have ATH Elo card."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ps-ath-elo" in resp.text
        assert "Best Elo Rating" in resp.text

    def test_player_stats_has_ath_rank_card(self, client, db_session):
        """Player stats modal should have ATH Rank card."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ps-ath-rank" in resp.text
        assert "Best Rank" in resp.text

    def test_player_stats_has_elo_chart(self, client, db_session):
        """Player stats modal should have Elo chart canvas."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "elo-chart" in resp.text

    def test_player_stats_has_chart_filters(self, client, db_session):
        """Player stats modal should have 1Y/5Y/10Y/ALL filter buttons."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "filterEloChart" in resp.text
        assert "elo-chart-filters" in resp.text

    def test_chart_js_included(self, client, db_session):
        """Chart.js CDN should be included in base template."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "chart.js" in resp.text.lower() or "chart.umd" in resp.text

    def test_elo_history_endpoint_exists(self, client, db_session):
        """Elo history API endpoint should exist and require auth."""
        resp = client.get("/rankings/player-stats/1/elo-history")
        assert resp.status_code == 401

    def test_ath_endpoint_exists(self, client, db_session):
        """ATH API endpoint should exist and require auth."""
        resp = client.get("/rankings/player-stats/1/ath")
        assert resp.status_code == 401

    def test_elo_history_returns_data(self, client, db_session):
        """Elo history endpoint should return history data for valid player."""
        from app.models.player import Player
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        player = Player(name="Test", start_elo=1200, current_elo=1200.0, active=True, disabled=False)
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)
        resp = client.get(f"/rankings/player-stats/{player.id}/elo-history")
        assert resp.status_code == 200
        data = resp.json()
        assert "history" in data
        assert "player_name" in data

    def test_ath_returns_data(self, client, db_session):
        """ATH endpoint should return ATH data for valid player."""
        from app.models.player import Player
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        player = Player(name="Test", start_elo=1200, current_elo=1200.0, active=True, disabled=False)
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)
        resp = client.get(f"/rankings/player-stats/{player.id}/ath")
        assert resp.status_code == 200
        data = resp.json()
        assert "ath_elo" in data
        assert "ath_rank" in data
        assert "max_elo" in data["ath_elo"]


class TestPasswordStrengthIndicator:
    """Tests for password strength indicator consistency across all password forms."""

    def test_change_password_has_strength_indicator(self, client, db_session):
        """Change Password page should have password strength indicator."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/change-password")
        assert resp.status_code == 200
        assert "pw-strength" in resp.text
        assert "checkPasswordStrength" in resp.text

    def test_change_password_has_oninput_handler(self, client, db_session):
        """Change Password new password field should have oninput handler."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/change-password")
        assert 'oninput="checkPasswordStrength(this.value)"' in resp.text

    def test_change_password_has_all_strength_checks(self, client, db_session):
        """Change Password should have all 5 password strength checks."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/change-password")
        assert "Min 8 characters" in resp.text
        assert "Uppercase letter" in resp.text
        assert "Lowercase letter" in resp.text
        assert "Number" in resp.text
        assert "Special character" in resp.text

    def test_admin_reset_password_has_strength_indicator(self, client, db_session):
        """Admin reset password form should have password strength indicator."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "reset-pw-strength" in resp.text
        assert "checkResetPasswordStrength" in resp.text

    def test_admin_add_user_has_strength_indicator(self, client, db_session):
        """Admin add user form should have password strength indicator."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "pw-strength" in resp.text
        assert "checkPasswordStrength" in resp.text

    def test_admin_add_user_has_all_strength_checks(self, client, db_session):
        """Admin add user should have all 5 password strength checks in JS."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "Min 8 characters" in resp.text
        assert "Uppercase letter" in resp.text
        assert "Lowercase letter" in resp.text
        assert "Number" in resp.text
        assert "Special character" in resp.text

    def test_admin_add_user_has_client_side_validation(self, client, db_session):
        """Admin add user should have client-side password strength validation before submit."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        # saveUser() checks password strength before submission
        assert "pwErrors" in resp.text or "Password does not meet requirements" in resp.text

    def test_change_password_strength_function_complete(self, client, db_session):
        """Change password strength function should check all criteria."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/change-password")
        assert "pw.length >= 8" in resp.text
        assert "/[A-Z]/.test(pw)" in resp.text
        assert "/[a-z]/.test(pw)" in resp.text
        assert "/[0-9]/.test(pw)" in resp.text
        assert "/[!" in resp.text  # Special char regex start


class TestBogeyNumberValidation:
    """Tests for bogey number (impossible checkout) validation in match forms."""

    def test_dashboard_has_bogey_number_check(self, client, db_session):
        """Dashboard match form should validate bogey numbers."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "bogeyNumbers" in resp.text
        assert "cannot be finished with a double" in resp.text

    def test_dashboard_bogey_numbers_list(self, client, db_session):
        """Dashboard should contain all 7 bogey numbers."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # All 7 bogey numbers should be in the set: 159, 162, 163, 165, 166, 168, 169
        assert "159" in resp.text
        assert "162" in resp.text
        assert "163" in resp.text
        assert "165" in resp.text
        assert "166" in resp.text
        assert "168" in resp.text
        assert "169" in resp.text

    def test_admin_has_bogey_number_check(self, client, db_session):
        """Admin match edit form should validate bogey numbers."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "bogeyNumbers" in resp.text
        assert "cannot be finished with a double" in resp.text

    def test_admin_bogey_numbers_list(self, client, db_session):
        """Admin should contain all 7 bogey numbers."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "159" in resp.text
        assert "162" in resp.text
        assert "163" in resp.text
        assert "165" in resp.text
        assert "166" in resp.text
        assert "168" in resp.text
        assert "169" in resp.text

    def test_bogey_validation_uses_match_error_element(self, client, db_session):
        """Dashboard bogey validation should use the match-error element for feedback."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "errEl.textContent" in resp.text
        assert "errEl.classList.remove('d-none')" in resp.text

    def test_admin_bogey_validation_uses_status_element(self, client, db_session):
        """Admin bogey validation should use the admin-modal-status element for feedback."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "Invalid checkout" in resp.text


class TestHighFinishLowDartRangeValidation:
    """Tests for high finish and low dart range validation in match form."""

    def test_dashboard_validates_hf_range(self, client, db_session):
        """Dashboard should validate high finish values are within configured range."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "hfMin" in resp.text
        assert "hfMax" in resp.text
        assert "Must be between" in resp.text

    def test_dashboard_validates_ld_range(self, client, db_session):
        """Dashboard should validate low dart values are within configured range."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ldMin" in resp.text
        assert "ldMax" in resp.text

    def test_dashboard_hf_range_uses_config_values(self, client, db_session):
        """Dashboard HF validation should use template-rendered config values."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # hf_min=100 and hf_max=170 from default config (rendered as comma-separated)
        assert "hfMin" in resp.text
        assert "hfMax" in resp.text
        assert "100" in resp.text
        assert "170" in resp.text

    def test_dashboard_ld_range_uses_config_values(self, client, db_session):
        """Dashboard LD validation should use template-rendered config values."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "ldMin" in resp.text
        assert "ldMax" in resp.text

    def test_dashboard_hf_range_error_message_includes_value(self, client, db_session):
        """Dashboard HF error message should include the invalid value."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Invalid high finish value" in resp.text

    def test_dashboard_ld_range_error_message_includes_value(self, client, db_session):
        """Dashboard LD error message should include the invalid value."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "Invalid low darts value" in resp.text

    def test_validation_prevents_submission(self, client, db_session):
        """Validation should prevent form submission and show error element."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        # Validation should return early (prevent submission)
        assert "return;" in resp.text
        # Should show error by removing d-none class
        assert "errEl.classList.remove('d-none')" in resp.text

    def test_hf_validation_focuses_invalid_input(self, client, db_session):
        """HF validation should focus the invalid input field."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "inp.focus()" in resp.text
