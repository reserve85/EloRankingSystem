"""Tests for database models and session management."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import inspect, text

from app.models import User, UserRole, Player, Match, ClubSettings, AuditLog


class TestUserModel:
    """Tests for User model."""

    def test_create_user(self, db_session):
        """Test creating a user with all required fields."""
        user = User(
            username="testuser",
            password_hash="hashed_password",
            role=UserRole.USER,
            active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.username == "testuser"
        assert user.password_hash == "hashed_password"
        assert user.role == UserRole.USER
        assert user.active is True
        assert user.created_at is not None
        assert user.updated_at is not None
        assert user.last_login_at is None

    def test_user_role_system(self, db_session):
        """Test SYSTEM role assignment."""
        user = User(
            username="admin_system",
            password_hash="hashed",
            role=UserRole.SYSTEM,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.role == UserRole.SYSTEM

    def test_user_role_admin(self, db_session):
        """Test ADMIN role assignment."""
        user = User(
            username="admin_user",
            password_hash="hashed",
            role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.role == UserRole.ADMIN

    def test_user_unique_username(self, db_session):
        """Test that duplicate usernames are rejected."""
        user1 = User(username="duplicate", password_hash="hash1", role=UserRole.USER)
        user2 = User(username="duplicate", password_hash="hash2", role=UserRole.USER)
        db_session.add(user1)
        db_session.commit()

        db_session.add(user2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()

    def test_user_repr(self, db_session):
        """Test User string representation."""
        user = User(
            username="repr_user",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        result = repr(user)
        assert "repr_user" in result
        assert "ADMIN" in result

    def test_user_disabled(self, db_session):
        """Test that active can be set to False."""
        user = User(
            username="disabled_user",
            password_hash="hash",
            role=UserRole.USER,
            active=False,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.active is False


class TestPlayerModel:
    """Tests for Player model."""

    def test_create_player(self, db_session):
        """Test creating a player with default values."""
        player = Player(name="John Doe")
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)

        assert player.id is not None
        assert player.name == "John Doe"
        assert player.start_elo == 1200
        assert player.current_elo == 1200.0
        assert player.active is True
        assert player.disabled is False
        assert player.last_match_date is None
        assert player.created_at is not None

    def test_create_player_custom_elo(self, db_session):
        """Test creating a player with custom start Elo."""
        player = Player(name="Pro Player", start_elo=1500, current_elo=1500.0)
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)

        assert player.start_elo == 1500
        assert player.current_elo == 1500.0

    def test_player_disabled(self, db_session):
        """Test player disabled state."""
        player = Player(name="Disabled Player", disabled=True)
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)

        assert player.disabled is True

    def test_player_repr(self, db_session):
        """Test Player string representation."""
        player = Player(name="Test Player")
        db_session.add(player)
        db_session.commit()
        db_session.refresh(player)

        result = repr(player)
        assert "Test Player" in result
        assert "1200" in result


class TestMatchModel:
    """Tests for Match model."""

    def _create_players(self, db_session):
        """Helper to create two players for match tests."""
        player_a = Player(name="Player A", current_elo=1200.0)
        player_b = Player(name="Player B", current_elo=1200.0)
        db_session.add_all([player_a, player_b])
        db_session.commit()
        db_session.refresh(player_a)
        db_session.refresh(player_b)
        return player_a, player_b

    def test_create_match(self, db_session):
        """Test creating a match with all required fields."""
        player_a, player_b = self._create_players(db_session)

        match = Match(
            date=date(2025, 1, 15),
            player_a_id=player_a.id,
            player_b_id=player_b.id,
            winner_id=player_a.id,
            loser_id=player_b.id,
            elo_before_a=1200.0,
            elo_before_b=1200.0,
            elo_after_a=1216.0,
            elo_after_b=1184.0,
            elo_change_a=16.0,
            elo_change_b=-16.0,
        )
        db_session.add(match)
        db_session.commit()
        db_session.refresh(match)

        assert match.id is not None
        assert match.date == date(2025, 1, 15)
        assert match.player_a_id == player_a.id
        assert match.player_b_id == player_b.id
        assert match.winner_id == player_a.id
        assert match.loser_id == player_b.id
        assert match.elo_before_a == 1200.0
        assert match.elo_before_b == 1200.0
        assert match.elo_after_a == 1216.0
        assert match.elo_after_b == 1184.0
        assert match.elo_change_a == 16.0
        assert match.elo_change_b == -16.0

    def test_match_relationships(self, db_session):
        """Test that match relationships resolve correctly."""
        player_a, player_b = self._create_players(db_session)

        match = Match(
            date=date(2025, 1, 15),
            player_a_id=player_a.id,
            player_b_id=player_b.id,
            winner_id=player_a.id,
            loser_id=player_b.id,
            elo_before_a=1200.0,
            elo_before_b=1200.0,
            elo_after_a=1216.0,
            elo_after_b=1184.0,
            elo_change_a=16.0,
            elo_change_b=-16.0,
        )
        db_session.add(match)
        db_session.commit()
        db_session.refresh(match)

        assert match.player_a.name == "Player A"
        assert match.player_b.name == "Player B"
        assert match.winner.name == "Player A"
        assert match.loser.name == "Player B"

    def test_match_repr(self, db_session):
        """Test Match string representation."""
        player_a, player_b = self._create_players(db_session)

        match = Match(
            date=date(2025, 6, 1),
            player_a_id=player_a.id,
            player_b_id=player_b.id,
            winner_id=player_a.id,
            loser_id=player_b.id,
            elo_before_a=1200.0,
            elo_before_b=1200.0,
            elo_after_a=1216.0,
            elo_after_b=1184.0,
            elo_change_a=16.0,
            elo_change_b=-16.0,
        )
        db_session.add(match)
        db_session.commit()
        db_session.refresh(match)

        result = repr(match)
        assert str(player_a.id) in result
        assert str(player_b.id) in result


class TestClubSettingsModel:
    """Tests for ClubSettings model."""

    def test_create_club_settings(self, db_session):
        """Test creating club settings with defaults."""
        settings = ClubSettings()
        db_session.add(settings)
        db_session.commit()
        db_session.refresh(settings)

        assert settings.id is not None
        assert settings.club_name == "Dart Club"
        assert settings.club_logo_path is None
        assert settings.default_elo == 1200
        assert settings.k_factor == 32.0
        assert settings.inactivity_months == 3

    def test_custom_club_settings(self, db_session):
        """Test creating club settings with custom values."""
        settings = ClubSettings(
            club_name="My Dart Club",
            default_elo=1500,
            k_factor=24.0,
            inactivity_months=6,
        )
        db_session.add(settings)
        db_session.commit()
        db_session.refresh(settings)

        assert settings.club_name == "My Dart Club"
        assert settings.default_elo == 1500
        assert settings.k_factor == 24.0
        assert settings.inactivity_months == 6

    def test_club_settings_repr(self, db_session):
        """Test ClubSettings string representation."""
        settings = ClubSettings(club_name="Test Club")
        db_session.add(settings)
        db_session.commit()
        db_session.refresh(settings)

        result = repr(settings)
        assert "Test Club" in result


class TestAuditLogModel:
    """Tests for AuditLog model."""

    def test_create_audit_log(self, db_session):
        """Test creating an audit log entry."""
        log = AuditLog(
            user_id=1,
            username="system",
            action="MATCH_CREATED",
            entity_type="match",
            entity_id=1,
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.id is not None
        assert log.timestamp is not None
        assert log.user_id == 1
        assert log.username == "system"
        assert log.action == "MATCH_CREATED"
        assert log.entity_type == "match"
        assert log.entity_id == 1
        assert log.ip_address == "127.0.0.1"
        assert log.user_agent == "Mozilla/5.0"

    def test_audit_log_minimal_fields(self, db_session):
        """Test audit log with only required fields."""
        log = AuditLog(action="LOGIN")
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.id is not None
        assert log.action == "LOGIN"
        assert log.user_id is None
        assert log.entity_type is None

    def test_audit_log_with_values(self, db_session):
        """Test audit log with old/new values."""
        log = AuditLog(
            action="USER_UPDATED",
            entity_type="user",
            entity_id=1,
            old_value='{"role": "USER"}',
            new_value='{"role": "ADMIN"}',
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert '"role": "USER"' in log.old_value
        assert '"role": "ADMIN"' in log.new_value

    def test_audit_log_repr(self, db_session):
        """Test AuditLog string representation."""
        log = AuditLog(action="TEST_ACTION", user_id=5, entity_type="test")
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        result = repr(log)
        assert "TEST_ACTION" in result
        assert "5" in result


class TestDatabaseSchema:
    """Tests for database schema integrity."""

    def test_all_tables_created(self, db_session):
        """Test that all expected tables exist in the database."""
        inspector = inspect(db_session.bind)
        tables = inspector.get_table_names()

        expected_tables = ["users", "players", "matches", "club_settings", "audit_log"]
        for table in expected_tables:
            assert table in tables, f"Table '{table}' not found in database"

    def test_users_table_columns(self, db_session):
        """Test that users table has all required columns."""
        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("users")}

        expected = {
            "id", "username", "password_hash", "role",
            "active", "created_at", "updated_at", "last_login_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_players_table_columns(self, db_session):
        """Test that players table has all required columns."""
        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("players")}

        expected = {
            "id", "name", "start_elo", "current_elo", "active",
            "disabled", "last_match_date", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_matches_table_columns(self, db_session):
        """Test that matches table has all required columns."""
        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("matches")}

        expected = {
            "id", "date", "player_a_id", "player_b_id",
            "winner_id", "loser_id",
            "elo_before_a", "elo_before_b", "elo_after_a", "elo_after_b",
            "elo_change_a", "elo_change_b",
            "created_by", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_club_settings_table_columns(self, db_session):
        """Test that club_settings table has all required columns."""
        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("club_settings")}

        expected = {
            "id", "club_name", "club_logo_path", "default_elo",
            "k_factor", "inactivity_months", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_audit_log_table_columns(self, db_session):
        """Test that audit_log table has all required columns."""
        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("audit_log")}

        expected = {
            "id", "timestamp", "user_id", "username", "action",
            "entity_type", "entity_id", "old_value", "new_value",
            "ip_address", "user_agent",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_foreign_keys_on_matches(self, db_session):
        """Test that matches table has proper foreign keys."""
        inspector = inspect(db_session.bind)
        fks = inspector.get_foreign_keys("matches")

        fk_tables = set()
        for fk in fks:
            fk_tables.add(fk["referred_table"])

        assert "players" in fk_tables
        assert "users" in fk_tables