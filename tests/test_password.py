"""Tests for password change and reset functionality."""


from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
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


def _create_user_db(db_session, username="user", password="Test1234", role=UserRole.USER, active=True):
    """Create a user directly in the database."""
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


# ── Password Validation Tests ──────────────────────────────────────────


class TestPasswordValidation:
    """Tests for password strength validation."""

    def test_valid_password_accepted(self):
        """Valid password should pass validation."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("SecurePass123")
        assert errors == []

    def test_too_short_rejected(self):
        """Password shorter than 8 chars should be rejected."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("Ab1")
        assert any("8 characters" in e for e in errors)

    def test_no_uppercase_rejected(self):
        """Password without uppercase should be rejected."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("lowercase123")
        assert any("uppercase" in e for e in errors)

    def test_no_lowercase_rejected(self):
        """Password without lowercase should be rejected."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("UPPERCASE123")
        assert any("lowercase" in e for e in errors)

    def test_no_number_rejected(self):
        """Password without number should be rejected."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("NoNumbersHere")
        assert any("number" in e for e in errors)

    def test_multiple_failures(self):
        """Multiple failures should return all errors."""
        from app.auth.password_validation import validate_password_strength
        errors = validate_password_strength("abc")
        assert len(errors) >= 3


# ── Change Password Tests ──────────────────────────────────────────────


class TestPasswordChange:
    """Tests for user changing their own password."""

    def test_successful_change(self, client, db_session):
        """User should be able to change their password successfully."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "successfully" in data["message"].lower()

    def test_wrong_current_password(self, client, db_session):
        """Wrong current password should fail."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        resp = client.post("/password/change", json={
            "current_password": "WrongPass123",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "incorrect" in data["message"].lower()

    def test_passwords_dont_match(self, client, db_session):
        """Mismatched new passwords should fail."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "Different123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "match" in data["message"].lower()

    def test_new_password_same_as_current(self, client, db_session):
        """New password same as current should fail."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "Test1234",
            "confirm_new_password": "Test1234",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "differ" in data["message"].lower()

    def test_weak_password_rejected(self, client, db_session):
        """Weak password should be rejected."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        # "alllowercase1" passes Pydantic min_length=8 but fails strength (no uppercase)
        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "alllowercase1",
            "confirm_new_password": "alllowercase1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "security requirements" in data["message"].lower()
        assert len(data["errors"]) > 0

    def test_new_password_actually_works(self, client, db_session):
        """After changing password, login with new password should work."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })

        # Logout
        client.post("/auth/logout")

        # Login with new password
        resp = client.post("/auth/login", data={
            "username": "user1",
            "password": "NewSecure123",
        })
        assert resp.status_code == 200

    def test_old_password_no_longer_works(self, client, db_session):
        """After changing password, old password should not work."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })

        client.post("/auth/logout")

        # Login with old password should fail
        resp = client.post("/auth/login", data={
            "username": "user1",
            "password": "Test1234",
        })
        assert resp.status_code == 401

    def test_unauthenticated_cannot_change(self, client, db_session):
        """Unauthenticated user cannot change password."""
        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })
        assert resp.status_code == 401

    def test_change_creates_audit_log(self, client, db_session):
        """Password change should create an audit log entry."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "NewSecure123",
            "confirm_new_password": "NewSecure123",
        })

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "PASSWORD_CHANGED"
        ).all()
        assert len(logs) >= 1

    def test_password_not_exposed_in_response(self, client, db_session):
        """Password hash should never appear in any response."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)

        # Get user info
        resp = client.get("/auth/me")
        data = resp.json()
        assert "password_hash" not in data
        assert "password" not in data

    def test_password_hash_not_stored_plaintext(self, db_session):
        """Password should be stored as hash, not plaintext."""
        user = User(
            username="hashtest",
            password_hash=hash_password("Test1234"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.password_hash != "Test1234"
        assert len(user.password_hash) > 20


# ── Admin Password Reset Tests ─────────────────────────────────────────


class TestPasswordReset:
    """Tests for admin resetting a user's password."""

    def test_admin_can_reset_password(self, client, db_session):
        """ADMIN should be able to reset a user's password."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")

        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "reset" in data["message"].lower()

    def test_system_can_reset_password(self, client, db_session):
        """SYSTEM should be able to reset a user's password."""
        _login_as(client, db_session, "sys", "SysPass1234", UserRole.SYSTEM)
        target = _create_user_db(db_session, "target", "Test1234")

        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_user_cannot_reset_password(self, client, db_session):
        """USER should NOT be able to reset passwords (403)."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)
        target = _create_user_db(db_session, "target", "Test1234")

        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 403

    def test_unauthenticated_cannot_reset(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.post("/password/reset", json={
            "user_id": 1,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 401

    def test_reset_nonexistent_user(self, client, db_session):
        """Resetting non-existent user should fail gracefully."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)

        resp = client.post("/password/reset", json={
            "user_id": 99999,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["message"].lower()

    def test_reset_passwords_dont_match(self, client, db_session):
        """Mismatched passwords should fail."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")

        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "Different123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_reset_weak_password_rejected(self, client, db_session):
        """Weak password should be rejected."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")

        # "alllowercase1" passes Pydantic min_length=8 but fails strength (no uppercase)
        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "alllowercase1",
            "confirm_new_password": "alllowercase1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "security requirements" in data["message"].lower()

    def test_reset_new_password_works(self, client, db_session):
        """After reset, new password should work for login."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")

        client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })

        client.post("/auth/logout")

        resp = client.post("/auth/login", data={
            "username": "target",
            "password": "ResetPass123",
        })
        assert resp.status_code == 200

    def test_reset_creates_audit_log(self, client, db_session):
        """Password reset should create an audit log entry."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")

        client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "PASSWORD_RESET_BY_ADMIN"
        ).all()
        assert len(logs) >= 1

    def test_admin_cannot_reset_system_user(self, client, db_session):
        """ADMIN should not be able to reset SYSTEM user password."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        sys_user = _create_user_db(db_session, "system2", "SysPass1234", UserRole.SYSTEM)

        resp = client.post("/password/reset", json={
            "user_id": sys_user.id,
            "new_password": "ResetPass123",
            "confirm_new_password": "ResetPass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "insufficient" in data["errors"][0].lower()


# ── UI Tests ───────────────────────────────────────────────────────────


class TestPasswordUI:
    """Tests for password management UI elements."""

    def test_change_password_page_exists(self, client, db_session):
        """Change password page should be accessible from header."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)
        resp = client.get("/ui/change-password")
        assert resp.status_code == 200
        assert "change-password-form" in resp.text
        assert "current_password" in resp.text
        assert "new_password" in resp.text
        assert "confirm_new_password" in resp.text
        assert "Change Password" in resp.text

    def test_header_has_change_password_link(self, client, db_session):
        """Header dropdown should contain change password link."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "/ui/change-password" in resp.text

    def test_dashboard_no_change_password_form(self, client, db_session):
        """Dashboard should NOT contain change password form."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)
        resp = client.get("/ui/dashboard")
        assert "change-password-form" not in resp.text

    def test_admin_has_reset_password_form(self, client, db_session):
        """Admin panel should contain reset password form."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        resp = client.get("/ui/admin")
        assert "reset-password-form" in resp.text
        assert "reset-pw-user" in resp.text
        assert "Reset User Password" in resp.text

    def test_password_change_endpoint_exists(self, client, db_session):
        """Password change endpoint should be accessible."""
        _login_as(client, db_session, "user1", "Test1234", UserRole.USER)
        resp = client.post("/password/change", json={
            "current_password": "Test1234",
            "new_password": "WeakPass",
            "confirm_new_password": "WeakPass",
        })
        # Even though password is weak, endpoint should respond (not 404)
        assert resp.status_code == 200
        assert "success" in resp.json()

    def test_password_reset_endpoint_exists(self, client, db_session):
        """Password reset endpoint should be accessible."""
        _login_as(client, db_session, "admin", "Admin1234", UserRole.ADMIN)
        target = _create_user_db(db_session, "target", "Test1234")
        resp = client.post("/password/reset", json={
            "user_id": target.id,
            "new_password": "WeakPass",
            "confirm_new_password": "WeakPass",
        })
        assert resp.status_code == 200
        assert "success" in resp.json()
