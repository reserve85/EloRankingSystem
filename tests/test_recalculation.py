"""Tests for historical Elo recalculation.

When a match is added, edited, or deleted, the complete affected timeline
must be recalculated chronologically.
"""


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


def _create_match_api(client, pa_id, pb_id, winner_id, match_date="2025-06-01"):
    """Create a match via API and return JSON."""
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    resp = client.post("/matches/", json={
        "date": match_date,
        "player_a_id": pa_id,
        "player_b_id": pb_id,
        "player1_score": score_a,
        "player2_score": score_b,
    })
    return resp


def _get_player_elo(client, player_id):
    """Get player's current Elo via API."""
    resp = client.get(f"/players/{player_id}")
    return resp.json()["current_elo"]


# ── Tests ───────────────────────────────────────────────────────────────


class TestRecalculationOnCreate:
    """Tests that creating a new match triggers recalculation."""

    def test_create_match_updates_elo_snapshots(self, client, db_session):
        """New match should have correct Elo before/after values."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        data = resp.json()

        assert data["elo_before_a"] == 1200.0
        assert data["elo_before_b"] == 1200.0
        assert data["elo_after_a"] > 1200.0
        assert data["elo_after_b"] < 1200.0
        assert data["elo_change_a"] + data["elo_change_b"] == pytest.approx(0, abs=1e-10)

    def test_elo_conservation_across_timeline(self, client, db_session):
        """Total Elo should be conserved across all matches."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-02")
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-03")

        elo_a = _get_player_elo(client, pa.id)
        elo_b = _get_player_elo(client, pb.id)

        # Total should be 2400 (1200 + 1200)
        assert elo_a + elo_b == pytest.approx(2400.0, abs=1e-10)


class TestRecalculationOnDelete:
    """Tests that deleting a match triggers recalculation of later matches."""

    def test_delete_first_match_recalculates_later(self, client, db_session):
        """Deleting the first match should recalculate all subsequent matches."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Match 1: Alice wins (2025-06-01)
        resp1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]

        # Match 2: Alice wins again (2025-06-02)
        resp2 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-02")
        m2_id = resp2.json()["id"]

        # Capture Elo after both matches
        elo_a_before_delete = _get_player_elo(client, pa.id)
        _get_player_elo(client, pb.id)
        assert elo_a_before_delete > 1200  # Alice won twice

        # Now delete match 1
        client.delete(f"/matches/{m1_id}")

        # After deletion, match 2 should be recalculated as if it were the first match
        elo_a_after = _get_player_elo(client, pa.id)
        _get_player_elo(client, pb.id)

        # Alice won one match from 1200 base, not two
        assert elo_a_after < elo_a_before_delete
        assert elo_a_after > 1200  # She still won match 2

        # Verify match 2 has updated Elo snapshots
        match2 = client.get(f"/matches/{m2_id}").json()
        assert match2["elo_before_a"] == 1200.0  # Reset to start_elo
        assert match2["elo_before_b"] == 1200.0

    def test_delete_later_match_preserves_earlier(self, client, db_session):
        """Deleting the last match should not change earlier matches."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]
        m1_elo_after_a = resp1.json()["elo_after_a"]

        resp2 = _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-02")
        m2_id = resp2.json()["id"]

        # Delete match 2 (the later one)
        client.delete(f"/matches/{m2_id}")

        # Match 1 should still have its original Elo values
        match1 = client.get(f"/matches/{m1_id}").json()
        assert match1["elo_after_a"] == pytest.approx(m1_elo_after_a, abs=1e-10)

    def test_delete_match_resets_player_elo_to_start(self, client, db_session):
        """Deleting all matches should reset player Elo to start_elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]

        client.delete(f"/matches/{m1_id}")

        assert _get_player_elo(client, pa.id) == 1200.0
        assert _get_player_elo(client, pb.id) == 1200.0

    def test_delete_recalculates_three_match_chain(self, client, db_session):
        """Deleting middle match in a 3-match chain recalculates correctly."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        pc = _create_player(db_session, "Charlie", elo=1200)

        # Match 1: Alice beats Bob (2025-06-01)
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")

        # Match 2: Alice beats Charlie (2025-06-02)
        resp2 = _create_match_api(client, pa.id, pc.id, pa.id, "2025-06-02")
        m2_id = resp2.json()["id"]

        # Match 3: Bob beats Alice (2025-06-03)
        _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-03")

        elo_a_full = _get_player_elo(client, pa.id)

        # Delete match 2 (Alice beats Charlie)
        client.delete(f"/matches/{m2_id}")

        elo_a_after = _get_player_elo(client, pa.id)

        # Alice: won match 1, lost match 3 - different from full timeline
        # Charlie's match is gone, so only Alice vs Bob matters
        assert elo_a_after != elo_a_full


class TestRecalculationOnEdit:
    """Tests that editing a match triggers recalculation of later matches."""

    def test_edit_winner_recalculates_later(self, client, db_session):
        """Changing the winner should recalculate all subsequent matches."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Match 1: Alice wins
        resp1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]

        # Match 2: Alice wins again
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-02")

        elo_a_before = _get_player_elo(client, pa.id)

        # Change match 1: Bob wins instead (0:3)
        client.put(f"/matches/{m1_id}", json={"player1_score": 0, "player2_score": 3})

        elo_a_after = _get_player_elo(client, pa.id)
        _get_player_elo(client, pb.id)

        # Alice now lost match 1 and won match 2
        # Her Elo should be lower than before
        assert elo_a_after < elo_a_before

    def test_edit_changes_later_elo_snapshots(self, client, db_session):
        """Editing a match should update Elo snapshots in later matches."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Match 1: Alice wins
        resp1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]

        # Match 2: Alice wins
        resp2 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-02")
        m2_id = resp2.json()["id"]

        # Match 2 should show Alice's Elo from after match 1
        m2_before = client.get(f"/matches/{m2_id}").json()
        m2_elo_before_a_orig = m2_before["elo_before_a"]

        # Change match 1: Bob wins (0:3)
        client.put(f"/matches/{m1_id}", json={"player1_score": 0, "player2_score": 3})

        # Match 2 now recalculated with Alice starting from lower Elo
        m2_after = client.get(f"/matches/{m2_id}").json()
        assert m2_after["elo_before_a"] < m2_elo_before_a_orig


class TestRecalculationDeterminism:
    """Tests that recalculation is deterministic."""

    def test_recalculation_order_by_date_asc(self, client, db_session):
        """Matches should be recalculated in chronological order."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        # Create matches out of order (but with different dates)
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-03")
        _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-01")
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-02")

        # Get all matches sorted
        matches = client.get("/matches/").json()

        # They should be sorted by date
        dates = [m["date"] for m in matches]
        assert dates == sorted(dates)

        # The second match (06-01) should have start Elo
        m_june1 = next(m for m in matches if m["date"] == "2025-06-01")
        assert m_june1["elo_before_a"] == 1200.0

    def test_player_current_elo_equals_latest_recalculated(self, client, db_session):
        """Player's current_elo should equal the elo_after from their latest match."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        resp2 = _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-02")
        m2_data = resp2.json()

        player_elo = _get_player_elo(client, pa.id)

        # Player's current Elo should match the last match's elo_after
        assert player_elo == pytest.approx(m2_data["elo_after_a"], abs=1e-10)

    def test_multiple_recalculations_produce_same_result(self, client, db_session):
        """Recalculating multiple times should produce the same result."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        resp2 = _create_match_api(client, pa.id, pb.id, pb.id, "2025-06-02")
        m2_id = resp2.json()["id"]

        elo_after_first_recalc = _get_player_elo(client, pa.id)

        # Editing match 2 with same data should trigger recalculation
        # but produce the same result
        client.put(f"/matches/{m2_id}", json={"date": "2025-06-02"})

        elo_after_second_recalc = _get_player_elo(client, pa.id)
        assert elo_after_second_recalc == pytest.approx(elo_after_first_recalc, abs=1e-10)


class TestRecalculationAuditLog:
    """Tests that recalculation writes audit log entries."""

    def test_recalculation_audit_on_create(self, client, db_session):
        """Creating a match should log a RANKING_RECALCULATED entry."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "RANKING_RECALCULATED"
        ).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert "affected_players" in log.new_value
        assert "matches_recalculated" in log.new_value

    def test_recalculation_audit_on_delete(self, client, db_session):
        """Deleting a match should log a RANKING_RECALCULATED entry."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        client.delete(f"/matches/{resp.json()['id']}")

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "RANKING_RECALCULATED"
        ).all()
        assert len(logs) >= 1


class TestRecalculationWithThirdPlayer:
    """Tests recalculation when a third player is involved."""

    def test_third_player_not_affected_by_earlier_matches(self, client, db_session):
        """Matches before the affected range should not be recalculated."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)
        pc = _create_player(db_session, "Charlie", elo=1200)

        # Match 1: Alice beats Charlie (2025-06-01)
        resp1 = _create_match_api(client, pa.id, pc.id, pa.id, "2025-06-01")
        m1_id = resp1.json()["id"]
        m1_elo_after = resp1.json()["elo_after_a"]

        # Match 2: Bob beats Charlie (2025-06-02)
        _create_match_api(client, pb.id, pc.id, pb.id, "2025-06-02")

        # Delete match 2
        # This should recalculate Charlie's timeline but NOT change match 1
        m2 = client.get("/matches/").json()
        m2_id = next(m for m in m2 if m["player_a_id"] == pb.id)["id"]
        client.delete(f"/matches/{m2_id}")

        # Match 1 should still have the same Elo values
        match1 = client.get(f"/matches/{m1_id}").json()
        assert match1["elo_after_a"] == pytest.approx(m1_elo_after, abs=1e-10)


class TestRecalculationEdgeCases:
    """Edge cases for recalculation."""

    def test_recalculate_after_deleting_all_matches(self, client, db_session):
        """Deleting all matches should reset all players to start_elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        client.delete(f"/matches/{resp.json()['id']}")

        assert _get_player_elo(client, pa.id) == 1200.0
        assert _get_player_elo(client, pb.id) == 1200.0

    def test_elo_after_sequential_wins_then_delete_first(self, client, db_session):
        """Alice wins 3, first deleted: Alice's Elo from 2 wins < 3 wins."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        r1 = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-02")
        _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-03")

        elo_a_three_wins = _get_player_elo(client, pa.id)

        client.delete(f"/matches/{r1.json()['id']}")

        elo_a_two_wins = _get_player_elo(client, pa.id)
        assert elo_a_two_wins < elo_a_three_wins
        assert elo_a_two_wins > 1200.0
