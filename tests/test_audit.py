"""Tests for audit logging."""


from app.models.user import User, UserRole
from app.models.player import Player
from app.models.audit_log import AuditLog
from app.auth.password import hash_password


def _login_as(client, db_session, username, password, role):
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


def _create_player(db_session, name="Player", elo=1200):
    player = Player(
        name=name, start_elo=elo, current_elo=float(elo),
        active=True, disabled=False,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _get_audit_logs(db_session, action=None):
    query = db_session.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    return query.all()


class TestLoginAudit:
    """Tests for login/logout audit logging."""

    def test_successful_login_logged(self, client, db_session):
        """Successful login should create LOGIN audit entry."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        logs = _get_audit_logs(db_session, "LOGIN")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "user"
        assert log.username == "user1"
        assert log.ip_address is not None

    def test_failed_login_logged(self, client, db_session):
        """Failed login should create LOGIN_FAILED audit entry."""
        # Create user
        user = User(
            username="testuser",
            password_hash=hash_password("correct"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Try wrong password
        client.post("/auth/login", data={"username": "testuser", "password": "wrong"})

        logs = _get_audit_logs(db_session, "LOGIN_FAILED")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.username == "testuser"
        assert log.ip_address is not None

    def test_logout_logged(self, client, db_session):
        """Logout should create LOGOUT audit entry."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        client.post("/auth/logout")

        logs = _get_audit_logs(db_session, "LOGOUT")
        assert len(logs) >= 1

    def test_password_never_logged(self, client, db_session):
        """Password should never appear in audit log values."""
        user = User(
            username="testuser",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        client.post("/auth/login", data={"username": "testuser", "password": "wrongpass"})

        logs = db_session.query(AuditLog).all()
        for log in logs:
            if log.new_value:
                assert "wrongpass" not in log.new_value
                assert "testpass" not in log.new_value
            if log.old_value:
                assert "wrongpass" not in log.old_value
                assert "testpass" not in log.old_value


class TestPlayerAudit:
    """Tests for player management audit logging."""

    def test_player_create_logged(self, client, db_session):
        """Player creation should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.post("/players/", json={"name": "New Player", "start_elo": 1200})

        logs = _get_audit_logs(db_session, "PLAYER_CREATED")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "player"
        assert log.entity_id is not None
        assert "New Player" in (log.new_value or "")

    def test_player_update_logged(self, client, db_session):
        """Player update should be logged with old/new values."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session, "Original")

        client.put(f"/players/{player.id}", json={"name": "Updated"})

        logs = _get_audit_logs(db_session, "PLAYER_UPDATED")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "player"
        assert log.entity_id == player.id

    def test_player_disable_logged(self, client, db_session):
        """Player disable should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session)

        client.post(f"/players/{player.id}/disable")

        logs = _get_audit_logs(db_session, "PLAYER_DISABLED")
        assert len(logs) >= 1

    def test_player_reactivate_logged(self, client, db_session):
        """Player reactivation should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session)
        player.disabled = True
        player.active = False
        db_session.commit()

        client.post(f"/players/{player.id}/reactivate")

        logs = _get_audit_logs(db_session, "PLAYER_REACTIVATED")
        assert len(logs) >= 1


class TestMatchAudit:
    """Tests for match audit logging."""

    def test_match_create_logged(self, client, db_session):
        """Match creation should be logged."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })

        logs = _get_audit_logs(db_session, "MATCH_CREATED")
        assert len(logs) >= 1

    def test_match_delete_logged(self, client, db_session):
        """Match deletion should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_id = resp.json()["id"]
        client.delete(f"/matches/{match_id}")

        logs = _get_audit_logs(db_session, "MATCH_DELETED")
        assert len(logs) >= 1
        assert logs[-1].entity_id == match_id

    def test_match_update_logged(self, client, db_session):
        """Match update should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_id = resp.json()["id"]

        client.put(f"/matches/{match_id}", json={"player1_score": 0, "player2_score": 3})

        logs = _get_audit_logs(db_session, "MATCH_UPDATED")
        assert len(logs) >= 1

    def test_ranking_recalculated_logged(self, client, db_session):
        """Match operations should trigger RANKING_RECALCULATED audit."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })

        logs = _get_audit_logs(db_session, "RANKING_RECALCULATED")
        assert len(logs) >= 1


def _create_user_db(db_session, username="user", password="pass", role=UserRole.USER, active=True):
    """Create a user directly in the database without logging in."""
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        active=active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestUserAudit:
    """Tests for user management audit logging."""

    def test_user_create_logged(self, client, db_session):
        """User creation should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.post("/users/", json={
            "username": "newuser", "password": "Pass123!", "role": "USER"
        })

        logs = _get_audit_logs(db_session, "USER_CREATED")
        assert len(logs) >= 1
        assert "newuser" in (logs[-1].new_value or "")

    def test_user_disable_logged(self, client, db_session):
        """User disable should be logged with USER_DISABLED action."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "pass", UserRole.USER)

        client.put(f"/users/{target.id}", json={"active": False})

        logs = _get_audit_logs(db_session, "USER_DISABLED")
        assert len(logs) >= 1

    def test_user_enable_logged(self, client, db_session):
        """User enable should be logged with USER_ENABLED action."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        user = _create_user_db(db_session, "disabled_user", "pass", UserRole.USER, active=False)

        client.put(f"/users/{user.id}", json={"active": True})

        logs = _get_audit_logs(db_session, "USER_ENABLED")
        assert len(logs) >= 1

    def test_password_reset_logged(self, client, db_session):
        """Password reset should be logged with PASSWORD_RESET action."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "pass", UserRole.USER)

        client.put(f"/users/{target.id}", json={"password": "NewPass123!"})

        logs = _get_audit_logs(db_session, "PASSWORD_RESET")
        assert len(logs) >= 1
        log = logs[-1]
        if log.new_value:
            assert "NewPass123!" not in log.new_value


class TestSettingsAudit:
    """Tests for club settings audit logging."""

    def test_settings_change_logged(self, client, db_session):
        """Settings change should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.put("/settings/", json={"club_name": "New Name"})

        logs = _get_audit_logs(db_session, "CLUB_SETTINGS_CHANGED")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "club_settings"
        assert "New Name" in (log.new_value or "")


class TestPdfAudit:
    """Tests for PDF export audit logging."""

    def test_pdf_export_logged(self, client, db_session):
        """PDF export should be logged."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        client.get("/reports/ranking/pdf?from_date=2025-06-01&to_date=2025-06-30")

        logs = _get_audit_logs(db_session, "PDF_EXPORTED")
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "report"


class TestAuditApi:
    """Tests for audit log API endpoint."""

    def test_admin_can_list_audit_logs(self, client, db_session):
        """ADMIN should be able to list audit logs."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/audit/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_user_cannot_list_audit_logs(self, client, db_session):
        """USER should not be able to list audit logs."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        resp = client.get("/audit/")
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list_audit_logs(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.get("/audit/")
        assert resp.status_code == 401

    def test_audit_log_filter_by_action(self, client, db_session):
        """Audit logs can be filtered by action."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session)
        client.post(f"/players/{player.id}/disable")

        resp = client.get("/audit/?action=PLAYER_DISABLED")
        assert resp.status_code == 200
        logs = resp.json()
        assert all(log["action"] == "PLAYER_DISABLED" for log in logs)

    def test_audit_log_filter_by_entity_type(self, client, db_session):
        """Audit logs can be filtered by entity type."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        player = _create_player(db_session)
        client.post(f"/players/{player.id}/disable")

        resp = client.get("/audit/?entity_type=player")
        assert resp.status_code == 200
        logs = resp.json()
        assert all(log["entity_type"] == "player" for log in logs)

    def test_audit_log_response_structure(self, client, db_session):
        """Audit log response should contain all required fields."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/audit/")
        logs = resp.json()
        assert len(logs) >= 1

        log = logs[0]
        required_fields = [
            "id", "timestamp", "action",
            "user_id", "username",
            "entity_type", "entity_id",
            "old_value", "new_value",
            "ip_address", "user_agent",
        ]
        for field in required_fields:
            assert field in log, f"Missing field: {field}"

    def test_admin_page_contains_audit_tab(self, client, db_session):
        """Admin page should contain audit log tab."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/ui/admin")
        assert "Audit Log" in resp.text
        assert "tab-audit" in resp.text
        assert "audit-table" in resp.text

    def test_audit_log_timestamp_uses_configured_format(self, client, db_session):
        """Audit log timestamps should be formatted with configured timezone and date format."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.get("/audit/")
        assert resp.status_code == 200
        logs = resp.json()
        if len(logs) > 0:
            ts = logs[0]["timestamp"]
            # Should not be ISO format (should be formatted with configured date format)
            assert "T" not in ts  # No ISO 'T' separator
            # Should contain time portion
            assert ":" in ts
