"""Tests for match management - service, routes, permissions, and Elo persistence."""

from datetime import date

import pytest

from app.models.player import Player
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.auth.password import hash_password


# ── Helpers ─────────────────────────────────────────────────────────────


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


def _create_player(db_session, name="Player", elo=1200):
    """Create a player directly in the database."""
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=True,
        disabled=False,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _create_match_via_api(client, player_a_id, player_b_id, winner_id, match_date="2025-06-01"):
    """Create a match via the API using Best-of-5 scores."""
    score_a = 3 if winner_id == player_a_id else 0
    score_b = 3 if winner_id == player_b_id else 0
    return client.post("/matches/", json={
        "date": match_date,
        "player_a_id": player_a_id,
        "player_b_id": player_b_id,
        "player1_score": score_a,
        "player2_score": score_b,
    })


# ── Match Creation Tests ────────────────────────────────────────────────


class TestMatchCreation:
    """Tests for match creation via API."""

    def test_create_match_as_user(self, client, db_session):
        """USER should be able to create a match."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        assert response.status_code == 201
        data = response.json()
        assert data["player_a_id"] == pa.id
        assert data["player_b_id"] == pb.id
        assert data["winner_id"] == pa.id
        assert data["loser_id"] == pb.id

    def test_create_match_as_admin(self, client, db_session):
        """ADMIN should be able to create a match."""
        _login_as(client, db_session, "admin1", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        assert response.status_code == 201

    def test_create_match_as_system(self, client, db_session):
        """SYSTEM should be able to create a match."""
        _login_as(client, db_session, "sys", "pass", UserRole.SYSTEM)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pb.id)
        assert response.status_code == 201
        assert response.json()["winner_id"] == pb.id

    def test_create_match_unauthenticated(self, client, db_session):
        """Unauthenticated user should not be able to create a match."""
        response = client.post("/matches/", json={
            "date": "2025-06-01",
            "player_a_id": 1,
            "player_b_id": 2,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert response.status_code == 401


# ── Validation Tests ────────────────────────────────────────────────────


class TestMatchValidation:
    """Tests for match validation."""

    def test_same_player_raises(self, client, db_session):
        """Player A cannot equal Player B."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")

        response = _create_match_via_api(client, pa.id, pa.id, pa.id)
        assert response.status_code == 422  # Pydantic validation

    def test_winner_not_a_player_raises(self, client, db_session):
        """Winner must be one of the two players."""
        _login_as(client, db_session, "user2", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")
        pc = _create_player(db_session, "Charlie")

        response = _create_match_via_api(client, pa.id, pb.id, pc.id)
        assert response.status_code == 422

    def test_winner_player_b(self, client, db_session):
        """Winner can be Player B."""
        _login_as(client, db_session, "user3", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pb.id)
        assert response.status_code == 201
        assert response.json()["winner_id"] == pb.id
        assert response.json()["loser_id"] == pa.id

    def test_nonexistent_player_a(self, client, db_session):
        """Player A must exist."""
        _login_as(client, db_session, "user4", "pass", UserRole.USER)
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, 99999, pb.id, pb.id)
        assert response.status_code == 404

    def test_nonexistent_player_b(self, client, db_session):
        """Player B must exist."""
        _login_as(client, db_session, "user5", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")

        response = _create_match_via_api(client, pa.id, 99999, pa.id)
        assert response.status_code == 404

    def test_invalid_date(self, client, db_session):
        """Invalid date should be rejected."""
        _login_as(client, db_session, "user6", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = client.post("/matches/", json={
            "date": "not-a-date",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert response.status_code == 422


# ── Elo Calculation Tests ───────────────────────────────────────────────


class TestMatchEloPersistence:
    """Tests for Elo rating updates after match creation."""

    def test_elo_stored_in_match(self, client, db_session):
        """Match should store Elo before/after/change for both players."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        assert response.status_code == 201
        data = response.json()

        assert data["elo_before_a"] == 1200.0
        assert data["elo_before_b"] == 1200.0
        assert data["elo_after_a"] > 1200.0  # Winner gains
        assert data["elo_after_b"] < 1200.0  # Loser loses
        assert data["elo_change_a"] > 0
        assert data["elo_change_b"] < 0

    def test_elo_conservation(self, client, db_session):
        """Total rating points should be conserved."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        data = response.json()

        assert data["elo_change_a"] + data["elo_change_b"] == pytest.approx(0, abs=1e-10)

    def test_player_elo_updated(self, client, db_session):
        """Player's current_elo should be updated after match."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_via_api(client, pa.id, pb.id, pa.id)

        # Fetch players via API
        resp_a = client.get(f"/players/{pa.id}")
        resp_b = client.get(f"/players/{pb.id}")

        assert resp_a.json()["current_elo"] > 1200.0
        assert resp_b.json()["current_elo"] < 1200.0

    def test_player_last_match_date_updated(self, client, db_session):
        """Player's last_match_date should be updated after match."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_via_api(client, pa.id, pb.id, pa.id, match_date="2025-03-15")

        resp_a = client.get(f"/players/{pa.id}")
        resp_b = client.get(f"/players/{pb.id}")

        assert resp_a.json()["last_match_date"] == "2025-03-15"
        assert resp_b.json()["last_match_date"] == "2025-03-15"

    def test_elo_with_unequal_ratings(self, client, db_session):
        """Elo change should reflect rating disparity."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1400)
        pb = _create_player(db_session, "Bob", elo=1200)

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        data = response.json()

        # Stronger player winning: small change
        assert 0 < data["elo_change_a"] < 16
        assert -16 < data["elo_change_b"] < 0

    def test_upset_larger_elo_change(self, client, db_session):
        """Upset (weaker player wins) should produce larger change."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1400)

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        data = response.json()

        # Weaker player wins: larger change
        assert data["elo_change_a"] > 16
        assert data["elo_change_b"] < -16


# ── Audit Log Tests ─────────────────────────────────────────────────────


class TestMatchAuditLog:
    """Tests for audit log entries on match operations."""

    def test_match_creation_logged(self, client, db_session):
        """Match creation should create an audit log entry."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        _create_match_via_api(client, pa.id, pb.id, pa.id)

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "MATCH_CREATED"
        ).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "match"
        assert log.entity_id is not None
        assert "player_a" in log.new_value

    def test_match_deletion_logged(self, client, db_session):
        """Match deletion should create an audit log entry."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = _create_match_via_api(client, pa.id, pb.id, pa.id)
        match_id = resp.json()["id"]

        client.delete(f"/matches/{match_id}")

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "MATCH_DELETED"
        ).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert log.entity_type == "match"
        assert log.entity_id == match_id


# ── List and Get Tests ──────────────────────────────────────────────────


class TestMatchListGet:
    """Tests for listing and getting matches."""

    def test_list_matches(self, client, db_session):
        """All authenticated users can list matches."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")
        _create_match_via_api(client, pa.id, pb.id, pa.id)

        response = client.get("/matches/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_get_match_by_id(self, client, db_session):
        """All authenticated users can get a match by ID."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = _create_match_via_api(client, pa.id, pb.id, pa.id)
        match_id = resp.json()["id"]

        response = client.get(f"/matches/{match_id}")
        assert response.status_code == 200
        assert response.json()["id"] == match_id

    def test_get_nonexistent_match(self, client, db_session):
        """Getting non-existent match should return 404."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)

        response = client.get("/matches/99999")
        assert response.status_code == 404

    def test_list_matches_unauthenticated(self, client, db_session):
        """Unauthenticated request should return 401."""
        response = client.get("/matches/")
        assert response.status_code == 401


# ── Delete Match Tests ─────────────────────────────────────────────────


class TestMatchDelete:
    """Tests for match deletion."""

    def test_admin_can_delete_match(self, client, db_session):
        """ADMIN should be able to delete a match."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = _create_match_via_api(client, pa.id, pb.id, pa.id)
        match_id = resp.json()["id"]

        response = client.delete(f"/matches/{match_id}")
        assert response.status_code == 200

        # Verify it's gone
        get_resp = client.get(f"/matches/{match_id}")
        assert get_resp.status_code == 404

    def test_system_can_delete_match(self, client, db_session):
        """SYSTEM should be able to delete a match."""
        _login_as(client, db_session, "sys", "pass", UserRole.SYSTEM)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = _create_match_via_api(client, pa.id, pb.id, pa.id)
        match_id = resp.json()["id"]

        response = client.delete(f"/matches/{match_id}")
        assert response.status_code == 200

    def test_user_cannot_delete_match(self, client, db_session):
        """USER should NOT be able to delete a match (403)."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        resp = _create_match_via_api(client, pa.id, pb.id, pa.id)
        match_id = resp.json()["id"]

        response = client.delete(f"/matches/{match_id}")
        assert response.status_code == 403

    def test_unauthenticated_cannot_delete(self, client, db_session):
        """Unauthenticated request should return 401."""
        response = client.delete("/matches/1")
        assert response.status_code == 401


# ── Match Response Structure ────────────────────────────────────────────


class TestMatchResponse:
    """Tests for match response structure."""

    def test_response_contains_all_fields(self, client, db_session):
        """Match response should contain all required fields."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        data = response.json()

        required_fields = [
            "id", "date", "player_a_id", "player_b_id",
            "winner_id", "loser_id",
            "elo_before_a", "elo_before_b",
            "elo_after_a", "elo_after_b",
            "elo_change_a", "elo_change_b",
            "created_by", "created_at", "updated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_created_by_stored(self, client, db_session):
        """Match should store the creator's user ID."""
        user = _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pa.id)
        data = response.json()

        assert data["created_by"] == user.id

    def test_date_stored_correctly(self, client, db_session):
        """Match date should be stored correctly."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")

        response = _create_match_via_api(client, pa.id, pb.id, pa.id, match_date="2025-12-25")
        data = response.json()

        assert data["date"] == "2025-12-25"


# ── Multiple Matches Tests ─────────────────────────────────────────────


class TestMultipleMatches:
    """Tests for multiple sequential matches."""

    def test_elo_accumulates(self, client, db_session):
        """Elo should accumulate across multiple matches."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Match 1: Alice wins
        _create_match_via_api(client, pa.id, pb.id, pa.id)
        resp_a1 = client.get(f"/players/{pa.id}")
        elo_a_after_1 = resp_a1.json()["current_elo"]
        assert elo_a_after_1 > 1200

        # Match 2: Alice wins again
        _create_match_via_api(client, pa.id, pb.id, pa.id, match_date="2025-06-02")
        resp_a2 = client.get(f"/players/{pa.id}")
        elo_a_after_2 = resp_a2.json()["current_elo"]
        assert elo_a_after_2 > elo_a_after_1

    def test_match_list_sorted(self, client, db_session):
        """Match list should be sorted by date, then created_at, then id."""
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_via_api(client, pa.id, pb.id, pa.id, match_date="2025-06-01")
        _create_match_via_api(client, pa.id, pb.id, pb.id, match_date="2025-06-02")
        _create_match_via_api(client, pa.id, pb.id, pa.id, match_date="2025-06-03")

        response = client.get("/matches/")
        matches = response.json()
        assert len(matches) == 3
        assert matches[0]["date"] <= matches[1]["date"] <= matches[2]["date"]