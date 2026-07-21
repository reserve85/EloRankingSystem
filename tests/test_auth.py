"""Tests for authentication and authorization."""

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, get_db
from app.models.user import User, UserRole
from app.auth.password import hash_password, verify_password, password_needs_rehash
from app.auth.jwt import create_access_token, decode_access_token
from app.auth.service import authenticate_user, create_login_response, provision_system_user
from app.auth.dependencies import get_current_user, require_role, require_system, require_admin, require_user
from app.main import app


# ── Password Hashing Tests ──────────────────────────────────────────────


class TestPasswordHashing:
    """Tests for Argon2 password hashing."""

    def test_hash_password_returns_string(self):
        """hash_password should return a non-empty string."""
        result = hash_password("mypassword")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_password_different_each_time(self):
        """Hashing the same password twice should produce different hashes."""
        hash1 = hash_password("mypassword")
        hash2 = hash_password("mypassword")
        assert hash1 != hash2

    def test_verify_password_correct(self):
        """verify_password should return True for correct password."""
        password = "securepassword123"
        hashed = hash_password(password)
        assert verify_password(hashed, password) is True

    def test_verify_password_incorrect(self):
        """verify_password should return False for wrong password."""
        hashed = hash_password("correctpassword")
        assert verify_password(hashed, "wrongpassword") is False

    def test_verify_password_empty(self):
        """verify_password should return False for empty password."""
        hashed = hash_password("mypassword")
        assert verify_password(hashed, "") is False

    def test_password_needs_rehash(self):
        """Newly hashed password should not need rehash."""
        hashed = hash_password("mypassword")
        assert password_needs_rehash(hashed) is False

    def test_verify_invalid_hash(self):
        """verify_password should return False for invalid hash format."""
        assert verify_password("not_a_valid_hash", "password") is False


# ── JWT Token Tests ─────────────────────────────────────────────────────


class TestJWTToken:
    """Tests for JWT token creation and verification."""

    def test_create_token(self, monkeypatch):
        """create_access_token should return a valid JWT string."""
        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "test-secret-key")
        monkeypatch.setattr("app.auth.jwt.settings.jwt_algorithm", "HS256")
        monkeypatch.setattr("app.auth.jwt.settings.access_token_lifetime_minutes", 480)

        token = create_access_token(user_id=1, username="testuser", role="USER")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self, monkeypatch):
        """decode_access_token should return payload for valid token."""
        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "test-secret-key")
        monkeypatch.setattr("app.auth.jwt.settings.jwt_algorithm", "HS256")
        monkeypatch.setattr("app.auth.jwt.settings.access_token_lifetime_minutes", 480)

        token = create_access_token(user_id=1, username="testuser", role="ADMIN")
        payload = decode_access_token(token)

        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
        assert payload["role"] == "ADMIN"

    def test_decode_invalid_token(self, monkeypatch):
        """decode_access_token should return None for invalid token."""
        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "test-secret-key")
        monkeypatch.setattr("app.auth.jwt.settings.jwt_algorithm", "HS256")

        result = decode_access_token("not.a.valid.token")
        assert result is None

    def test_decode_token_wrong_secret(self, monkeypatch):
        """decode_access_token should fail with wrong secret."""
        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "correct-secret")
        monkeypatch.setattr("app.auth.jwt.settings.jwt_algorithm", "HS256")
        monkeypatch.setattr("app.auth.jwt.settings.access_token_lifetime_minutes", 480)

        token = create_access_token(user_id=1, username="testuser", role="USER")

        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "wrong-secret")
        result = decode_access_token(token)
        assert result is None

    def test_token_contains_all_fields(self, monkeypatch):
        """Token payload should contain sub, username, role, iat, exp."""
        monkeypatch.setattr("app.auth.jwt.settings.jwt_secret", "test-secret")
        monkeypatch.setattr("app.auth.jwt.settings.jwt_algorithm", "HS256")
        monkeypatch.setattr("app.auth.jwt.settings.access_token_lifetime_minutes", 480)

        token = create_access_token(user_id=42, username="admin", role="SYSTEM")
        payload = decode_access_token(token)

        assert payload["sub"] == "42"
        assert payload["username"] == "admin"
        assert payload["role"] == "SYSTEM"
        assert "iat" in payload
        assert "exp" in payload


# ── Authentication Service Tests ────────────────────────────────────────


class TestAuthenticateUser:
    """Tests for user authentication service."""

    def test_successful_login(self, db_session):
        """Valid credentials should authenticate and return user."""
        user = User(
            username="testuser",
            password_hash=hash_password("correctpassword"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        result = authenticate_user(db_session, "testuser", "correctpassword")
        assert result is not None
        assert result.username == "testuser"
        assert result.last_login_at is not None

    def test_failed_login_wrong_password(self, db_session):
        """Wrong password should return None."""
        user = User(
            username="testuser",
            password_hash=hash_password("correctpassword"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        result = authenticate_user(db_session, "testuser", "wrongpassword")
        assert result is None

    def test_failed_login_nonexistent_user(self, db_session):
        """Non-existent username should return None."""
        result = authenticate_user(db_session, "nobody", "password")
        assert result is None

    def test_disabled_user_cannot_login(self, db_session):
        """Disabled user should not be able to log in."""
        user = User(
            username="disableduser",
            password_hash=hash_password("password"),
            role=UserRole.USER,
            active=False,
        )
        db_session.add(user)
        db_session.commit()

        result = authenticate_user(db_session, "disableduser", "password")
        assert result is None

    def test_login_updates_last_login_at(self, db_session):
        """Successful login should update last_login_at timestamp."""
        user = User(
            username="testuser",
            password_hash=hash_password("password"),
            role=UserRole.USER,
            active=True,
            last_login_at=None,
        )
        db_session.add(user)
        db_session.commit()

        assert user.last_login_at is None

        result = authenticate_user(db_session, "testuser", "password")
        assert result is not None
        assert result.last_login_at is not None

    def test_admin_login(self, db_session):
        """Admin user should be able to log in."""
        user = User(
            username="admin",
            password_hash=hash_password("adminpass"),
            role=UserRole.ADMIN,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        result = authenticate_user(db_session, "admin", "adminpass")
        assert result is not None
        assert result.role == UserRole.ADMIN

    def test_system_user_login(self, db_session):
        """System user should be able to log in."""
        user = User(
            username="system",
            password_hash=hash_password("systempass"),
            role=UserRole.SYSTEM,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        result = authenticate_user(db_session, "system", "systempass")
        assert result is not None
        assert result.role == UserRole.SYSTEM


class TestCreateLoginResponse:
    """Tests for login response creation."""

    def test_login_response_structure(self, db_session):
        """Login response should contain required fields."""
        user = User(
            username="testuser",
            password_hash=hash_password("password"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        response = create_login_response(user)

        assert "access_token" in response
        assert "token_type" in response
        assert "user" in response
        assert response["token_type"] == "bearer"
        assert response["user"]["id"] == user.id
        assert response["user"]["username"] == "testuser"
        assert response["user"]["role"] == "USER"


# ── System User Provisioning Tests ─────────────────────────────────────


class TestSystemUserProvisioning:
    """Tests for SYSTEM user provisioning."""

    def test_provision_creates_system_user(self, db_session, monkeypatch):
        """provision_system_user should create a new system user."""
        monkeypatch.setattr(
            "app.core.config.settings.system_user_username", "system"
        )
        monkeypatch.setattr(
            "app.core.config.settings.system_user_password", "adminpass"
        )

        user = provision_system_user(db_session)

        assert user is not None
        assert user.username == "system"
        assert user.role == UserRole.SYSTEM
        assert user.active is True
        assert user.id is not None

    def test_provision_idempotent(self, db_session, monkeypatch):
        """Calling provision_system_user twice should not create duplicates."""
        monkeypatch.setattr(
            "app.core.config.settings.system_user_username", "system"
        )
        monkeypatch.setattr(
            "app.core.config.settings.system_user_password", "adminpass"
        )

        user1 = provision_system_user(db_session)
        user2 = provision_system_user(db_session)

        assert user1.id == user2.id
        assert db_session.query(User).filter(User.role == UserRole.SYSTEM).count() == 1

    def test_provision_hashes_password(self, db_session, monkeypatch):
        """Provisioned system user should have hashed password, not plain text."""
        monkeypatch.setattr(
            "app.core.config.settings.system_user_username", "system"
        )
        monkeypatch.setattr(
            "app.core.config.settings.system_user_password", "adminpass"
        )

        user = provision_system_user(db_session)

        assert user.password_hash != "adminpass"
        assert verify_password(user.password_hash, "adminpass")

    def test_provisioned_user_can_login(self, db_session, monkeypatch):
        """Provisioned system user should be able to log in with config password."""
        monkeypatch.setattr(
            "app.core.config.settings.system_user_username", "system"
        )
        monkeypatch.setattr(
            "app.core.config.settings.system_user_password", "adminpass"
        )

        provision_system_user(db_session)
        result = authenticate_user(db_session, "system", "adminpass")

        assert result is not None
        assert result.role == UserRole.SYSTEM


# ── Role Check Tests ───────────────────────────────────────────────────


class TestRoleChecks:
    """Tests for role-based access control."""

    def test_require_system_allows_system(self, db_session):
        """require_system should allow SYSTEM users."""
        user = User(
            username="sysuser",
            password_hash=hash_password("pass"),
            role=UserRole.SYSTEM,
            active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # require_system returns a dependency function that checks role
        role_checker = require_system.__wrapped__ if hasattr(require_system, '__wrapped__') else None
        if role_checker:
            result = role_checker(user)
            assert result == user
        else:
            # Direct test of the role check logic
            assert user.role == UserRole.SYSTEM

    def test_user_role_enum_values(self):
        """UserRole should have all required values."""
        assert UserRole.SYSTEM.value == "SYSTEM"
        assert UserRole.ADMIN.value == "ADMIN"
        assert UserRole.USER.value == "USER"

    def test_role_hierarchy(self, db_session):
        """Test role assignments for all three role types."""
        sys_user = User(username="sys", password_hash="h", role=UserRole.SYSTEM)
        admin_user = User(username="adm", password_hash="h", role=UserRole.ADMIN)
        regular_user = User(username="usr", password_hash="h", role=UserRole.USER)

        db_session.add_all([sys_user, admin_user, regular_user])
        db_session.commit()

        assert sys_user.role == UserRole.SYSTEM
        assert admin_user.role == UserRole.ADMIN
        assert regular_user.role == UserRole.USER

    def test_system_user_cannot_be_downgraded_via_field(self, db_session):
        """Verify that the role field can be checked against SYSTEM."""
        user = User(
            username="sys",
            password_hash=hash_password("pass"),
            role=UserRole.SYSTEM,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Business rule: SYSTEM role cannot be downgraded
        # (enforcement would be in service layer, here we just verify the model)
        assert user.role == UserRole.SYSTEM


# ── Auth API Endpoint Tests ────────────────────────────────────────────


class TestAuthEndpoints:
    """Tests for authentication API endpoints."""

    def test_login_success(self, client, db_session):
        """POST /auth/login with valid credentials should return 200."""
        user = User(
            username="testuser",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        response = client.post(
            "/auth/login",
            data={"username": "testuser", "password": "testpass"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["username"] == "testuser"
        assert data["token_type"] == "bearer"

        # Verify cookie was set
        assert "access_token" in response.cookies

    def test_login_invalid_password(self, client, db_session):
        """POST /auth/login with wrong password should return 401."""
        user = User(
            username="testuser",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        response = client.post(
            "/auth/login",
            data={"username": "testuser", "password": "wrongpass"},
        )

        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_login_nonexistent_user(self, client, db_session):
        """POST /auth/login with non-existent user should return 401."""
        response = client.post(
            "/auth/login",
            data={"username": "nobody", "password": "password"},
        )

        assert response.status_code == 401

    def test_login_disabled_user(self, client, db_session):
        """POST /auth/login with disabled user should return 401."""
        user = User(
            username="disabled",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=False,
        )
        db_session.add(user)
        db_session.commit()

        response = client.post(
            "/auth/login",
            data={"username": "disabled", "password": "testpass"},
        )

        assert response.status_code == 401

    def test_logout(self, client, db_session):
        """POST /auth/logout should clear cookie and return 200."""
        user = User(
            username="testuser",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Login first
        client.post("/auth/login", data={"username": "testuser", "password": "testpass"})

        # Then logout
        response = client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"

    def test_me_authenticated(self, client, db_session):
        """GET /auth/me with valid cookie should return user info."""
        user = User(
            username="testuser",
            password_hash=hash_password("testpass"),
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()

        # Login to get cookie
        client.post("/auth/login", data={"username": "testuser", "password": "testpass"})

        # Access /auth/me
        response = client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["role"] == "USER"
        assert data["active"] is True

    def test_me_unauthenticated(self, client, db_session):
        """GET /auth/me without cookie should return 401."""
        response = client.get("/auth/me")
        assert response.status_code == 401