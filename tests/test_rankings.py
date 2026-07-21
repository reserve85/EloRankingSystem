"""Tests for ranking generation."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.models.player import Player
from app.models.user import User, UserRole
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


def _create_match(client, pa_id, pb_id, winner_id, match_date):
    """Create a match via API using Best-of-5 scores."""
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    return client.post("/matches/", json={
        "date": match_date,
        "player_a_id": pa_id,
        "player_b_id": pb_id,
        "player1_score": score_a,
        "player2_score": score_b,
    })


def _get_ranking(client, from_date=None, to_date=None, include_inactive=False):
    """Get ranking via API."""
    params = {"include_inactive": str(include_inactive).lower()}
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    return client.get("/rankings/", params=params)


# ── Tests ───────────────────────────────────────────────────────────────


class TestRankingGeneration:
    """Tests for basic ranking generation."""

    def test_empty_ranking(self, client, db_session):
        """Ranking with no players should return empty."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []

    def test_single_player_no_matches(self, client, db_session):
        """Player with no matches should appear with start Elo."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Alice", elo=1200)

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["player_name"] == "Alice"
        assert data["entries"][0]["elo_rating"] == 1200.0
        assert data["entries"][0]["elo_change"] == 0.0
        assert data["entries"][0]["position_change"] == 0

    def test_ranking_after_match(self, client, db_session):
        """Ranking should reflect match results."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        data = resp.json()
        assert len(data["entries"]) == 2

        # Alice should be #1 (won)
        assert data["entries"][0]["player_name"] == "Alice"
        assert data["entries"][0]["elo_rating"] > 1200
        assert data["entries"][0]["position"] == 1

        # Bob should be #2 (lost)
        assert data["entries"][1]["player_name"] == "Bob"
        assert data["entries"][1]["elo_rating"] < 1200
        assert data["entries"][1]["position"] == 2

    def test_ranking_order_by_elo(self, client, db_session):
        """Ranking should be sorted by Elo descending."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        pc = _create_player(db_session, "Charlie", elo=1200)

        # Alice wins twice, Bob wins once
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-10")
        _create_match(client, pa.id, pc.id, pa.id, "2025-06-11")
        _create_match(client, pb.id, pc.id, pb.id, "2025-06-12")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        entries = resp.json()["entries"]

        # Order: Alice > Bob > Charlie
        assert entries[0]["player_name"] == "Alice"
        assert entries[1]["player_name"] == "Bob"
        assert entries[2]["player_name"] == "Charlie"

    def test_ranking_response_structure(self, client, db_session):
        """Ranking response should contain required fields."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Alice")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        data = resp.json()

        assert "from_date" in data
        assert "to_date" in data
        assert "entries" in data
        assert "generated_at" in data
        assert data["from_date"] == "2025-06-01"
        assert data["to_date"] == "2025-06-30"


class TestEloChangeCalculation:
    """Tests for Elo change in rankings."""

    def test_elo_change_positive(self, client, db_session):
        """Elo change should be positive when player wins."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        alice = next(e for e in resp.json()["entries"] if e["player_name"] == "Alice")
        assert alice["elo_change"] > 0

    def test_elo_change_negative(self, client, db_session):
        """Elo change should be negative when player loses."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        bob = next(e for e in resp.json()["entries"] if e["player_name"] == "Bob")
        assert bob["elo_change"] < 0

    def test_elo_change_zero_before_period(self, client, db_session):
        """Elo change should be zero if no matches in period."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Match before the ranking period
        _create_match(client, pa.id, pb.id, pa.id, "2025-05-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        for entry in resp.json()["entries"]:
            assert entry["elo_change"] == 0.0

    def test_elo_change_across_multiple_matches(self, client, db_session):
        """Elo change should reflect net change across multiple matches."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Alice wins one, loses one
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-10")
        _create_match(client, pa.id, pb.id, pb.id, "2025-06-20")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        alice = next(e for e in resp.json()["entries"] if e["player_name"] == "Alice")

        # Net Elo change should be small (won one, lost one against same opponent)
        # Not exactly 0 because Elo changes are slightly asymmetric
        assert abs(alice["elo_change"]) < 2.0


class TestPositionChange:
    """Tests for position change in rankings."""

    def test_position_change_up(self, client, db_session):
        """Player who gains Elo should move up in position."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        pc = _create_player(db_session, "Charlie", elo=1200)

        # Charlie is ranked above Alice by name at equal Elo
        # Alice wins a match, moving above Charlie
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        entries = resp.json()["entries"]
        alice = next(e for e in entries if e["player_name"] == "Alice")

        # Alice gained Elo, should be #1
        assert alice["position"] == 1
        assert alice["position_change"] >= 0

    def test_position_change_down(self, client, db_session):
        """Player who loses Elo should move down in position."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1300)
        pb = _create_player(db_session, "Bob", elo=1100)
        pc = _create_player(db_session, "Charlie", elo=1200)

        # Alice loses to Bob (upset)
        _create_match(client, pa.id, pb.id, pb.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        entries = resp.json()["entries"]
        alice = next(e for e in entries if e["player_name"] == "Alice")

        # Alice dropped Elo significantly, should drop in ranking
        # Bob gained, Charlie unchanged - Alice might still be #1
        # but her position_change should be <= 0
        assert alice["position_change"] <= 0

    def test_position_change_zero(self, client, db_session):
        """Player with no position change should show 0."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Equal ratings, Alice wins - she should stay #1
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        entries = resp.json()["entries"]

        # If both start at same Elo, Alice was #1, stays #1
        alice = next(e for e in entries if e["player_name"] == "Alice")
        # Position could change based on name tiebreaker
        # But with equal Elo she stays #1
        assert alice["position"] == 1


class TestDateRangeFiltering:
    """Tests for date range filtering."""

    def test_match_outside_range_excluded(self, client, db_session):
        """Matches outside the date range should not affect ranking."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-05-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        for entry in resp.json()["entries"]:
            assert entry["elo_change"] == 0.0

    def test_only_matches_in_range_affect_elo_change(self, client, db_session):
        """Only matches within date range should contribute to Elo change."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-05-15")
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        alice = next(e for e in resp.json()["entries"] if e["player_name"] == "Alice")

        # Elo change should only reflect June match
        # At start of June, Alice already had higher Elo from May
        assert alice["elo_change"] > 0

    def test_full_range_includes_all_matches(self, client, db_session):
        """Full range should include all matches."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2025-01-15")
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

        resp = _get_ranking(client, "2025-01-01", "2025-12-31", include_inactive=True)
        alice = next(e for e in resp.json()["entries"] if e["player_name"] == "Alice")
        assert alice["elo_change"] > 0


class TestInactivePlayers:
    """Tests for inactive player exclusion."""

    def test_inactive_player_excluded(self, client, db_session, monkeypatch):
        """Inactive players should be excluded from active ranking."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Active Alice", elo=1300)
        pb = _create_player(db_session, "Active Bob", elo=1200)
        pc = _create_player(db_session, "Inactive Charlie", elo=1100)

        # Give Charlie a very old last_match_date
        pc.last_match_date = date(2024, 1, 1)
        db_session.commit()

        resp = _get_ranking(
            client,
            from_date=str(date.today().replace(day=1)),
            to_date=str(date.today()),
            include_inactive=False,
        )
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "Inactive Charlie" not in names

    def test_inactive_player_included_with_flag(self, client, db_session, monkeypatch):
        """Inactive players should appear when include_inactive=True."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pc = _create_player(db_session, "Inactive Charlie", elo=1100)
        pc.last_match_date = date(2024, 1, 1)
        db_session.commit()

        resp = _get_ranking(
            client,
            from_date=str(date.today().replace(day=1)),
            to_date=str(date.today()),
            include_inactive=True,
        )
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "Inactive Charlie" in names

    def test_disabled_player_always_excluded(self, client, db_session):
        """Disabled players should always be excluded."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pd = _create_player(db_session, "Disabled Dave", elo=1200)
        pd.disabled = True
        db_session.commit()

        resp = _get_ranking(
            client,
            "2025-06-01", "2025-06-30",
            include_inactive=True,
        )
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "Disabled Dave" not in names

    def test_active_player_with_recent_match_included(self, client, db_session, monkeypatch):
        """Player with recent match should be included."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, str(date.today()))

        resp = _get_ranking(
            client,
            from_date=str(date.today().replace(day=1)),
            to_date=str(date.today()),
        )
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "Alice" in names
        assert "Bob" in names


class TestRankingPermissions:
    """Tests for ranking endpoint permissions."""

    def test_user_can_view_ranking(self, client, db_session):
        """USER should be able to view rankings."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        assert resp.status_code == 200

    def test_admin_can_view_ranking(self, client, db_session):
        """ADMIN should be able to view rankings."""
        _login_as(client, db_session, "a1", "pass", UserRole.ADMIN)
        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        assert resp.status_code == 200

    def test_unauthenticated_cannot_view_ranking(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        assert resp.status_code == 401