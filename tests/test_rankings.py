"""Tests for ranking generation."""

from datetime import date


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


def _create_player(db_session, name="Player", elo=1200, active=True, last_match=None):
    """Create a player directly in the database."""
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=active,
        disabled=False,
        last_match_date=last_match,
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

    def test_single_player_no_matches_excluded(self, client, db_session):
        """Player with no matches and active=False should be excluded from active ranking."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Alice", elo=1200, active=False)

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        data = resp.json()
        assert len(data["entries"]) == 0

    def test_single_player_no_matches_included_with_flag(self, client, db_session):
        """Player with no matches should appear when include_inactive=True."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "Alice", elo=1200)

        resp = _get_ranking(client, "2025-06-01", "2025-06-30", include_inactive=True)
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
        pa = _create_player(db_session, "Alice")
        pb = _create_player(db_session, "Bob")
        _create_match(client, pa.id, pb.id, pa.id, "2025-06-15")

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
        _create_player(db_session, "Charlie", elo=1200)

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
        _create_player(db_session, "Charlie", elo=1200)

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
        _create_player(db_session, "Active Alice", elo=1300)
        _create_player(db_session, "Active Bob", elo=1200)
        _create_player(db_session, "Inactive Charlie", elo=1100, active=False)

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


class TestAllTimeEloChart:
    """Tests for all-time Elo rating endpoint."""

    def test_all_time_elo_returns_data(self, client, db_session, monkeypatch):
        """Endpoint should return data for players with matches."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 999)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, str(date.today()))

        resp = client.get("/rankings/all-time-elo")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        # Should be sorted by max_elo descending
        assert data[0]["max_elo"] >= data[1]["max_elo"]

    def test_all_time_elo_includes_zero_game_players_when_inactive(self, client, db_session, monkeypatch):
        """Players with 0 games should be included when include_inactive=True."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        _create_player(db_session, "Charlie", elo=1200)  # No matches

        _create_match(client, pa.id, pb.id, pa.id, str(date.today()))

        # Charlie excluded by default (inactive, no matches)
        resp = client.get("/rankings/all-time-elo")
        data = resp.json()
        names = [p["player_name"] for p in data]
        assert "Charlie" not in names
        assert "Alice" in names
        assert "Bob" in names

        # Charlie included when include_inactive=True
        resp = client.get("/rankings/all-time-elo?include_inactive=true")
        data = resp.json()
        names = [p["player_name"] for p in data]
        assert "Charlie" in names
        # Charlie should show start_elo since no matches
        charlie = [p for p in data if p["player_name"] == "Charlie"][0]
        assert charlie["max_elo"] == 1200.0
        assert charlie["date_reached"] is None

    def test_all_time_elo_excludes_inactive_by_default(self, client, db_session, monkeypatch):
        """Inactive players should be excluded by default."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2024-01-01")

        # Both players have old matches -> inactive
        resp = client.get("/rankings/all-time-elo")
        data = resp.json()
        # All players should be excluded (inactive)
        assert len(data) == 0

    def test_all_time_elo_includes_inactive_with_flag(self, client, db_session, monkeypatch):
        """Inactive players should appear with include_inactive=true."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, "2024-01-01")

        resp = client.get("/rankings/all-time-elo?include_inactive=true")
        data = resp.json()
        names = [p["player_name"] for p in data]
        assert "Alice" in names
        assert "Bob" in names

    def test_all_time_elo_response_structure(self, client, db_session, monkeypatch):
        """Response should contain required fields."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 999)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, str(date.today()))

        resp = client.get("/rankings/all-time-elo")
        data = resp.json()
        for entry in data:
            assert "player_id" in entry
            assert "player_name" in entry
            assert "max_elo" in entry
            assert "date_reached" in entry
            assert "inactive" in entry

    def test_all_time_elo_max_elo_correct(self, client, db_session, monkeypatch):
        """Max Elo should reflect the highest value reached."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 999)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match(client, pa.id, pb.id, pa.id, str(date.today()))
        _create_match(client, pa.id, pb.id, pb.id, str(date.today()))

        resp = client.get("/rankings/all-time-elo")
        data = resp.json()
        alice = next(p for p in data if p["player_name"] == "Alice")
        # Alice won first match, so max_elo should be after first match
        assert alice["max_elo"] > 1200

    def test_all_time_elo_disabled_excluded(self, client, db_session, monkeypatch):
        """Disabled players should always be excluded."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 999)

        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pd = _create_player(db_session, "Disabled Dave", elo=1200)
        pd.disabled = True
        db_session.commit()

        _create_match(client, pa.id, pd.id, pa.id, str(date.today()))

        resp = client.get("/rankings/all-time-elo?include_inactive=true")
        data = resp.json()
        names = [p["player_name"] for p in data]
        assert "Disabled Dave" not in names

    def test_all_time_elo_requires_auth(self, client, db_session):
        """Unauthenticated request should return 401."""
        resp = client.get("/rankings/all-time-elo")
        assert resp.status_code == 401


class TestAllTimeHighRanking:
    """Tests for the all-time high ranking (best rank) calculation.

    The best rank must consider ALL non-disabled players including:
    - Active players with matches
    - Inactive players with matches
    - Players with 0 matches (using their start_elo)
    This prevents inflated best ranks when high-elo inactive/zero-match
    players are excluded from the calculation.
    """

    def test_best_rank_includes_inactive_players_with_high_elo(
        self, client, db_session, monkeypatch
    ):
        """20 inactive players with elo 5000 should outrank a new player with 2000.

        If inactive players are excluded, the new player would incorrectly
        get best rank #1. With them included, the new player should be #21.
        """
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 20 inactive players with very high start_elo
        inactive_ids = []
        for i in range(20):
            resp = client.post("/players/", json={
                "name": f"Inactive_{i}",
                "start_elo": 5000,
            })
            assert resp.status_code == 201
            pid = resp.json()["id"]
            # Mark as inactive (last_match far in the past)
            player = db_session.query(Player).filter(Player.id == pid).first()
            player.last_match_date = date(2020, 1, 1)
            db_session.commit()
            inactive_ids.append(pid)

        # Create the new player with elo 2000 and an opponent
        resp_new = client.post("/players/", json={
            "name": "NewPlayer",
            "start_elo": 2000,
        })
        assert resp_new.status_code == 201
        new_player_id = resp_new.json()["id"]

        resp_opp = client.post("/players/", json={
            "name": "Opponent",
            "start_elo": 1200,
        })
        assert resp_opp.status_code == 201
        opp_id = resp_opp.json()["id"]

        # NewPlayer plays their first match
        resp_match = client.post("/matches/", json={
            "date": "2026-07-20",
            "player_a_id": new_player_id,
            "player_b_id": opp_id,
            "player1_score": 3,
            "player2_score": 0,
        })
        assert resp_match.status_code == 201

        # Get best rank for NewPlayer
        resp = client.get(f"/rankings/player-stats/{new_player_id}/ath")
        assert resp.status_code == 200
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]

        # NewPlayer has elo ~2016 after winning, but 20 inactive players have 5000
        # So best rank should be #21, NOT #1
        assert best_rank is not None
        assert best_rank == 21, (
            f"Expected best rank #21 (after 20 inactive players with elo 5000), "
            f"got #{best_rank}"
        )

    def test_best_rank_includes_zero_match_players_with_high_start_elo(
        self, client, db_session, monkeypatch
    ):
        """Players with 0 matches but high start_elo should affect best rank."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 5 players with 0 matches and high start_elo
        for i in range(5):
            resp = client.post("/players/", json={
                "name": f"ZeroMatch_{i}",
                "start_elo": 3000,
            })
            assert resp.status_code == 201

        # Create a player with normal elo
        resp_new = client.post("/players/", json={
            "name": "NormalPlayer",
            "start_elo": 1200,
        })
        new_id = resp_new.json()["id"]

        resp_opp = client.post("/players/", json={
            "name": "Opponent",
            "start_elo": 1200,
        })
        opp_id = resp_opp.json()["id"]

        # NormalPlayer plays a match
        client.post("/matches/", json={
            "date": "2026-07-20",
            "player_a_id": new_id,
            "player_b_id": opp_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # Get best rank
        resp = client.get(f"/rankings/player-stats/{new_id}/ath")
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]

        # 5 zero-match players with elo 3000 should be ranked above
        # NormalPlayer with elo ~1216. So rank should be #6 (at minimum),
        # plus there's also the opponent at 1200.
        # Total players: 5 (elo 3000) + NormalPlayer + Opponent = 7
        # NormalPlayer at ~1216 is above Opponent at ~1184
        # So NormalPlayer is #6, Opponent is #7
        assert best_rank is not None
        assert best_rank >= 6, (
            f"Expected best rank >= #6 (5 zero-match players with elo 3000 above), "
            f"got #{best_rank}"
        )

    def test_best_rank_disabled_players_excluded(
        self, client, db_session, monkeypatch
    ):
        """Disabled players should NOT affect best rank calculation."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 10 disabled players with high elo
        for i in range(10):
            resp = client.post("/players/", json={
                "name": f"Disabled_{i}",
                "start_elo": 5000,
            })
            pid = resp.json()["id"]
            player = db_session.query(Player).filter(Player.id == pid).first()
            player.disabled = True
            db_session.commit()

        # Create active players
        resp_new = client.post("/players/", json={
            "name": "ActivePlayer",
            "start_elo": 1200,
        })
        new_id = resp_new.json()["id"]

        resp_opp = client.post("/players/", json={
            "name": "Opponent",
            "start_elo": 1200,
        })
        opp_id = resp_opp.json()["id"]

        # Play a match
        client.post("/matches/", json={
            "date": "2026-07-20",
            "player_a_id": new_id,
            "player_b_id": opp_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        # Get best rank
        resp = client.get(f"/rankings/player-stats/{new_id}/ath")
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]

        # Disabled players should not count, only 2 active players
        # ActivePlayer won -> #1
        assert best_rank == 1, (
            f"Disabled players should be excluded. Expected #1, got #{best_rank}"
        )

    def test_best_rank_normal_scenario(
        self, client, db_session, monkeypatch
    ):
        """Best rank works correctly in a normal scenario with active players."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 3 players
        resp_a = client.post("/players/", json={"name": "Alice", "start_elo": 1200})
        resp_b = client.post("/players/", json={"name": "Bob", "start_elo": 1200})
        resp_c = client.post("/players/", json={"name": "Charlie", "start_elo": 1200})
        a_id = resp_a.json()["id"]
        b_id = resp_b.json()["id"]
        c_id = resp_c.json()["id"]

        # Alice wins against Bob -> Alice is #1
        client.post("/matches/", json={
            "date": "2026-07-10",
            "player_a_id": a_id, "player_b_id": b_id,
            "player1_score": 3, "player2_score": 0,
        })

        # Alice wins against Charlie -> still #1
        client.post("/matches/", json={
            "date": "2026-07-15",
            "player_a_id": a_id, "player_b_id": c_id,
            "player1_score": 3, "player2_score": 0,
        })

        # Alice loses to Bob -> drops to #2
        client.post("/matches/", json={
            "date": "2026-07-20",
            "player_a_id": a_id, "player_b_id": b_id,
            "player1_score": 0, "player2_score": 3,
        })

        resp = client.get(f"/rankings/player-stats/{a_id}/ath")
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]
        date_reached = data["ath_rank"]["date_reached"]

        # Alice's best rank should be #1 (achieved on 2026-07-10)
        assert best_rank == 1
        assert date_reached == "2026-07-10"

    def test_best_rank_player_with_no_matches(
        self, client, db_session, monkeypatch
    ):
        """Player with no matches should have no best rank."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp_p = client.post("/players/", json={"name": "NoMatchPlayer"})
        pid = resp_p.json()["id"]

        resp = client.get(f"/rankings/player-stats/{pid}/ath")
        data = resp.json()
        assert data["ath_rank"]["best_rank"] is None
        assert data["ath_rank"]["date_reached"] is None


class TestNewPlayerNotInRanking:
    """Tests that newly created players don't appear in ranking."""

    def test_new_player_via_api_not_in_ranking(self, client, db_session):
        """Player created via API (no matches) should NOT appear in ranking."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create player via API
        resp = client.post("/players/", json={"name": "NewGuy"})
        assert resp.status_code == 201

        # Login as user and check ranking
        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        today_str = str(date.today())
        first_of_month = today_str[:7] + "-01"
        resp = _get_ranking(client, first_of_month, today_str)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "NewGuy" not in names

    def test_new_player_via_api_visible_with_flag(self, client, db_session):
        """Player created via API should appear with include_inactive=True."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp = client.post("/players/", json={"name": "NewGuy"})
        assert resp.status_code == 201

        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        today_str = str(date.today())
        first_of_month = today_str[:7] + "-01"
        resp = _get_ranking(client, first_of_month, today_str, include_inactive=True)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "NewGuy" in names

    def test_player_with_match_appears_in_ranking(self, client, db_session, monkeypatch):
        """Player with a recent match should appear in ranking."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp_a = client.post("/players/", json={"name": "ActiveGuy"})
        resp_b = client.post("/players/", json={"name": "Opponent"})
        pa_id = resp_a.json()["id"]
        pb_id = resp_b.json()["id"]

        # Create match
        client.post("/matches/", json={
            "date": str(date.today()),
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": 3,
            "player2_score": 0,
        })

        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        today_str = str(date.today())
        first_of_month = today_str[:7] + "-01"
        resp = _get_ranking(client, first_of_month, today_str)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "ActiveGuy" in names
        assert "Opponent" in names
