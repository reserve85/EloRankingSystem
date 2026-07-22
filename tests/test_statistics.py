"""Tests for dart match statistics (180s, high finishes, low darts)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.user import User
from app.models.player import Player
from app.models.match import Match
from app.models.audit_log import AuditLog
from app.auth.password import hash_password
from app.main import app


TEST_DATABASE_URL = "sqlite:///./test_statistics.db"
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


def _create_user(db_session, username="admin", role="ADMIN"):
    user = User(username=username, password_hash=hash_password("AdminPass123"), role=role, active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_players(db_session):
    player_a = Player(name="Player A", start_elo=1200, current_elo=1200, active=True, disabled=False)
    player_b = Player(name="Player B", start_elo=1200, current_elo=1200, active=True, disabled=False)
    db_session.add_all([player_a, player_b])
    db_session.commit()
    db_session.refresh(player_a)
    db_session.refresh(player_b)
    return player_a, player_b


def _login(client, username="admin", password="AdminPass123"):
    resp = client.post("/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200


# ── High Finish Validation ─────────────────────────────────────────────

class TestHighFinishValidation:
    """Test high finish values are validated against configured range."""

    def test_valid_high_finish_accepted(self, client, db_session):
        """High finish within default range [100, 170] is accepted."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [100, 170],
            "player_b_high_finishes": [120],
        })
        assert resp.status_code == 201

    def test_high_finish_below_min_rejected(self, client, db_session):
        """High finish below configured minimum is rejected."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [99],
        })
        assert resp.status_code == 422

    def test_high_finish_above_max_rejected(self, client, db_session):
        """High finish above configured maximum is rejected."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [171],
        })
        assert resp.status_code == 422

    def test_high_finish_boundaries_accepted(self, client, db_session):
        """Exact boundary values (min and max) are accepted."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [100],
            "player_b_high_finishes": [170],
        })
        assert resp.status_code == 201

    def test_player_b_high_finish_validated(self, client, db_session):
        """Player B's high finishes are also validated."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_b_high_finishes": [50],
        })
        assert resp.status_code == 422

    def test_high_finish_validation_on_update(self, client, db_session):
        """High finish validation applies on match update too."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        # Create valid match
        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_id = resp.json()["id"]

        # Try invalid update
        resp = client.put(f"/matches/{match_id}", json={
            "player_a_high_finishes": [99],
        })
        assert resp.status_code == 422

    def test_empty_high_finishes_accepted(self, client, db_session):
        """Empty lists are accepted (default behavior)."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [],
            "player_b_high_finishes": [],
        })
        assert resp.status_code == 201


# ── Low Darts Validation ──────────────────────────────────────────────

class TestLowDartsValidation:
    """Test low darts values are validated against configured range."""

    def test_valid_low_darts_accepted(self, client, db_session):
        """Low darts within default range [9, 21] is accepted."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_low_darts": [9, 15, 21],
        })
        assert resp.status_code == 201

    def test_low_darts_below_min_rejected(self, client, db_session):
        """Low darts below configured minimum is rejected."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_low_darts": [8],
        })
        assert resp.status_code == 422

    def test_low_darts_above_max_rejected(self, client, db_session):
        """Low darts above configured maximum is rejected."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_b_low_darts": [22],
        })
        assert resp.status_code == 422

    def test_low_darts_boundaries_accepted(self, client, db_session):
        """Exact boundary values (min and max) are accepted."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_low_darts": [9],
            "player_b_low_darts": [21],
        })
        assert resp.status_code == 201


# ── 180s Statistics ────────────────────────────────────────────────────

class Test180sStatistics:
    """Test 180s count storage and retrieval."""

    def test_180s_defaults_to_zero(self, client, db_session):
        """180s defaults to 0 when not provided."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_180s"] == 0
        assert data["player_b_180s"] == 0

    def test_180s_stored_correctly(self, client, db_session):
        """180s count is stored and returned correctly."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 1,
            "player_a_180s": 3,
            "player_b_180s": 1,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_180s"] == 3
        assert data["player_b_180s"] == 1

    def test_180s_retrieved_by_id(self, client, db_session):
        """180s count is correctly returned when fetching match by ID."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 5,
            "player_b_180s": 2,
        })
        match_id = resp.json()["id"]

        resp = client.get(f"/matches/{match_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_a_180s"] == 5
        assert data["player_b_180s"] == 2

    def test_180s_in_list_response(self, client, db_session):
        """180s count is included in match list response."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 4,
            "player_b_180s": 0,
        })

        resp = client.get("/matches/")
        assert resp.status_code == 200
        matches = resp.json()
        assert len(matches) == 1
        assert matches[0]["player_a_180s"] == 4
        assert matches[0]["player_b_180s"] == 0

    def test_180s_rejected_if_negative(self, client, db_session):
        """Negative 180s count is rejected."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": -1,
        })
        assert resp.status_code == 422

    def test_180s_update(self, client, db_session):
        """180s count can be updated via match update."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 1,
        })
        match_id = resp.json()["id"]

        resp = client.put(f"/matches/{match_id}", json={
            "player_a_180s": 5,
        })
        assert resp.status_code == 200
        assert resp.json()["player_a_180s"] == 5


# ── High Finishes Storage and Retrieval ────────────────────────────────

class TestHighFinishesStorage:
    """Test high finishes stored and retrieved correctly."""

    def test_high_finishes_stored_on_create(self, client, db_session):
        """High finishes are stored when creating a match."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 1,
            "player_a_high_finishes": [120, 140, 170],
            "player_b_high_finishes": [100],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_high_finishes"] == [120, 140, 170]
        assert data["player_b_high_finishes"] == [100]

    def test_high_finishes_retrieved_by_id(self, client, db_session):
        """High finishes are returned when fetching match by ID."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [105, 130],
        })
        match_id = resp.json()["id"]

        resp = client.get(f"/matches/{match_id}")
        assert resp.status_code == 200
        assert resp.json()["player_a_high_finishes"] == [105, 130]

    def test_high_finishes_default_empty(self, client, db_session):
        """High finishes default to empty list when not provided."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_high_finishes"] is None or data["player_a_high_finishes"] == []
        assert data["player_b_high_finishes"] is None or data["player_b_high_finishes"] == []

    def test_high_finishes_update(self, client, db_session):
        """High finishes can be updated on an existing match."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_id = resp.json()["id"]

        resp = client.put(f"/matches/{match_id}", json={
            "player_a_high_finishes": [110, 150],
        })
        assert resp.status_code == 200
        assert resp.json()["player_a_high_finishes"] == [110, 150]

    def test_high_finishes_in_list_response(self, client, db_session):
        """High finishes are included in match list response."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_high_finishes": [100],
        })

        resp = client.get("/matches/")
        assert resp.status_code == 200
        assert resp.json()[0]["player_a_high_finishes"] == [100]


# ── Low Darts Storage and Retrieval ────────────────────────────────────

class TestLowDartsStorage:
    """Test low darts stored and retrieved correctly."""

    def test_low_darts_stored_on_create(self, client, db_session):
        """Low darts are stored when creating a match."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 2,
            "player_a_low_darts": [12, 15, 18],
            "player_b_low_darts": [9, 21],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_low_darts"] == [12, 15, 18]
        assert data["player_b_low_darts"] == [9, 21]

    def test_low_darts_retrieved_by_id(self, client, db_session):
        """Low darts are returned when fetching match by ID."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_low_darts": [9],
        })
        match_id = resp.json()["id"]

        resp = client.get(f"/matches/{match_id}")
        assert resp.status_code == 200
        assert resp.json()["player_a_low_darts"] == [9]

    def test_low_darts_default_empty(self, client, db_session):
        """Low darts default to empty list when not provided."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["player_a_low_darts"] is None or data["player_a_low_darts"] == []
        assert data["player_b_low_darts"] is None or data["player_b_low_darts"] == []

    def test_low_darts_update(self, client, db_session):
        """Low darts can be updated on an existing match."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
        })
        match_id = resp.json()["id"]

        resp = client.put(f"/matches/{match_id}", json={
            "player_b_low_darts": [10, 14],
        })
        assert resp.status_code == 200
        assert resp.json()["player_b_low_darts"] == [10, 14]


# ── Statistics and Elo Recalculation ───────────────────────────────────

class TestStatisticsPreservedDuringRecalculation:
    """Test that historical Elo recalculation does NOT overwrite statistics."""

    def test_statistics_preserved_after_new_match_triggers_recalculation(
        self, client, db_session
    ):
        """Adding a new match that triggers recalc preserves existing stats."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        # Create first match with statistics
        resp = client.post("/matches/", json={
            "date": "2026-07-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 2,
            "player_b_180s": 1,
            "player_a_high_finishes": [120],
            "player_b_high_finishes": [100],
            "player_a_low_darts": [9],
            "player_b_low_darts": [15],
        })
        match1_id = resp.json()["id"]

        # Create second match (triggers recalculation of timeline)
        resp = client.post("/matches/", json={
            "date": "2026-07-15",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 0,
            "player2_score": 3,
            "player_a_180s": 0,
            "player_b_180s": 3,
        })
        assert resp.status_code == 201

        # Verify first match's statistics are preserved
        resp = client.get(f"/matches/{match1_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_a_180s"] == 2
        assert data["player_b_180s"] == 1
        assert data["player_a_high_finishes"] == [120]
        assert data["player_b_high_finishes"] == [100]
        assert data["player_a_low_darts"] == [9]
        assert data["player_b_low_darts"] == [15]

    def test_statistics_preserved_after_match_edit_triggers_recalculation(
        self, client, db_session
    ):
        """Editing a match triggers recalc but preserves stats on other matches."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        # Create two matches
        resp1 = client.post("/matches/", json={
            "date": "2026-07-01",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 5,
            "player_a_high_finishes": [140],
            "player_a_low_darts": [12],
        })
        match1_id = resp1.json()["id"]

        resp2 = client.post("/matches/", json={
            "date": "2026-07-15",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 2,
            "player_b_180s": 4,
            "player_b_high_finishes": [150],
            "player_b_low_darts": [10],
        })
        match2_id = resp2.json()["id"]

        # Edit first match score (triggers full recalculation)
        client.put(f"/matches/{match1_id}", json={
            "player1_score": 3,
            "player2_score": 1,
        })

        # Verify second match's statistics are preserved
        resp = client.get(f"/matches/{match2_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["player_b_180s"] == 4
        assert data["player_b_high_finishes"] == [150]
        assert data["player_b_low_darts"] == [10]


# ── Statistics Deleted with Match ──────────────────────────────────────

class TestStatisticsDeletedWithMatch:
    """Test that deleting a match removes its statistics."""

    def test_match_statistics_removed_on_delete(self, client, db_session):
        """Deleting a match removes all its statistics data."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 3,
            "player_a_high_finishes": [120, 140],
            "player_a_low_darts": [9, 12],
        })
        match_id = resp.json()["id"]

        # Verify statistics exist
        resp = client.get(f"/matches/{match_id}")
        assert resp.json()["player_a_180s"] == 3

        # Delete match
        resp = client.delete(f"/matches/{match_id}")
        assert resp.status_code == 200

        # Match (and its statistics) no longer exists
        resp = client.get(f"/matches/{match_id}")
        assert resp.status_code == 404


# ── Audit Logging for Statistics ───────────────────────────────────────

class TestStatisticsAuditLog:
    """Test that statistics changes appear in audit logs."""

    def test_statistics_included_in_create_audit(self, client, db_session):
        """Match creation audit log includes statistics data."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 2,
            "player_a_high_finishes": [100],
            "player_a_low_darts": [9],
        })

        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "MATCH_CREATED"
        ).first()
        assert audit is not None
        assert "180s_a" in audit.new_value
        assert "high_finishes_a" in audit.new_value
        assert "low_darts_a" in audit.new_value

    def test_statistics_included_in_update_audit(self, client, db_session):
        """Match update audit log includes statistics data."""
        _create_user(db_session)
        _login(client)
        pa, pb = _create_players(db_session)

        resp = client.post("/matches/", json={
            "date": "2026-07-22",
            "player_a_id": pa.id,
            "player_b_id": pb.id,
            "player1_score": 3,
            "player2_score": 0,
            "player_a_180s": 1,
        })
        match_id = resp.json()["id"]

        client.put(f"/matches/{match_id}", json={
            "player_a_180s": 5,
            "player_a_high_finishes": [150],
        })

        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "MATCH_UPDATED"
        ).first()
        assert audit is not None
        assert "statistics" in audit.old_value
        assert "statistics" in audit.new_value


# ── Migration Test ─────────────────────────────────────────────────────

class TestMigration:
    """Test that the migration runs cleanly on an existing database."""

    def test_new_columns_exist_in_schema(self, db_session):
        """Verify the new statistics columns exist in the matches table."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        columns = {col["name"] for col in inspector.get_columns("matches")}

        assert "player_a_180s" in columns
        assert "player_b_180s" in columns
        assert "player_a_high_finishes" in columns
        assert "player_b_high_finishes" in columns
        assert "player_a_low_darts" in columns
        assert "player_b_low_darts" in columns

    def test_new_columns_have_correct_defaults(self, db_session):
        """Verify that new columns have sensible defaults for existing rows."""
        from datetime import date as date_type

        # Insert a match directly without statistics fields (simulating pre-migration data)
        pa, pb = _create_players(db_session)

        match = Match(
            date=date_type(2026, 7, 22),
            player_a_id=pa.id,
            player_b_id=pb.id,
            winner_id=pa.id,
            loser_id=pb.id,
            elo_before_a=1200.0,
            elo_before_b=1200.0,
            elo_after_a=1216.0,
            elo_after_b=1184.0,
            elo_change_a=16.0,
            elo_change_b=-16.0,
        )
        db_session.add(match)
        db_session.commit()

        # Refresh and check defaults
        db_session.refresh(match)
        assert match.player_a_180s == 0
        assert match.player_b_180s == 0
        assert match.player_a_high_finishes is None or match.player_a_high_finishes == []
        assert match.player_b_high_finishes is None or match.player_b_high_finishes == []
        assert match.player_a_low_darts is None or match.player_a_low_darts == []
        assert match.player_b_low_darts is None or match.player_b_low_darts == []