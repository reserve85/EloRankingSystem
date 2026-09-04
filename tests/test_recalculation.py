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
class TestBoundaryInitialization:
    """Fix #12 - boundary initialization of ``_recalculate_elo_timeline``.

    Players with a match history before the recalculation window must enter
    the window at their pre-window rating instead of being reset to
    ``start_elo``, which corrupted snapshots and ``current_elo`` values.
    """

    @staticmethod
    def _expected(ra: float, rb: float) -> float:
        """Standard Elo expected score for rating ra against rb."""
        return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

    def _assert_equals_full_replay(self, client) -> None:
        """Assert all stored snapshots equal a manual full-history replay."""
        matches = sorted(
            client.get("/matches/").json(),
            key=lambda m: (m["date"], m["created_at"], m["id"]),
        )
        ratings: dict[int, float] = {}
        for m in matches:
            pa, pb = m["player_a_id"], m["player_b_id"]
            ra = ratings.get(pa, 1200.0)
            rb = ratings.get(pb, 1200.0)
            ea = self._expected(ra, rb)
            aa = 1.0 if m["winner_id"] == pa else 0.0
            ab = 1.0 - aa
            k = 32.0
            na, nb = ra + k * (aa - ea), rb + k * (ab - (1.0 - ea))
            ratings[pa], ratings[pb] = na, nb
            assert m["elo_before_a"] == pytest.approx(ra, abs=1e-9)
            assert m["elo_after_a"] == pytest.approx(na, abs=1e-9)
            assert m["elo_before_b"] == pytest.approx(rb, abs=1e-9)
            assert m["elo_after_b"] == pytest.approx(nb, abs=1e-9)

    def test_pre_window_rating_preserved(self, client, db_session):
        """A non-affected player keeps their pre-window Elo, not start_elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        eve = _create_player(db_session, "Eve", elo=1200)
        frank = _create_player(db_session, "Frank", elo=1200)
        alice = _create_player(db_session, "Alice", elo=1200)
        charlie = _create_player(db_session, "Charlie", elo=1200)

        # Jan 5: Eve beats Frank -> Frank drops to 1184
        _create_match_api(client, eve.id, frank.id, eve.id, "2025-01-05")
        # Jun 1: Alice beats Charlie (this match will be deleted)
        _create_match_api(client, alice.id, charlie.id, alice.id, "2025-06-01")
        # Jun 2: Charlie beats Frank
        m3 = _create_match_api(
            client, charlie.id, frank.id, charlie.id, "2025-06-02"
        ).json()

        # Sanity: Frank lost his first match
        assert _get_player_elo(client, frank.id) < 1200.0

        # Delete the Jun 1 match -> affected = {Alice, Charlie}
        m2 = next(m for m in client.get("/matches/").json() if m["date"] == "2025-06-01")
        client.delete(f"/matches/{m2['id']}")

        m3_after = client.get(f"/matches/{m3['id']}").json()
        # Frank is NOT directly affected: he enters the recalculation window at
        # his pre-window rating (1184 after losing to Eve), NOT at start_elo.
        assert m3_after["elo_before_b"] == pytest.approx(1184.0, abs=1e-9)
        assert m3_after["elo_after_b"] < m3_after["elo_before_b"]
        # Charlie IS directly affected: he enters at start_elo.
        assert m3_after["elo_before_a"] == pytest.approx(1200.0, abs=1e-9)

        # Alice's only match was deleted -> reset to start_elo.
        assert _get_player_elo(client, alice.id) == 1200.0

    def test_boundary_init_equals_full_replay(self, client, db_session):
        """Window recalculation with boundary init equals full-history replay."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1200)
        c = _create_player(db_session, "Carl", elo=1200)
        d = _create_player(db_session, "Dana", elo=1200)

        # Jan 5: Bob beats Alice -> Bob has pre-window history
        _create_match_api(client, a.id, b.id, b.id, "2025-01-05")
        # Jun 1: Bob beats Carl
        _create_match_api(client, b.id, c.id, b.id, "2025-06-01")
        # Jun 2: Dana beats Carl
        m3 = _create_match_api(client, c.id, d.id, d.id, "2025-06-02").json()

        # Flip the Jun 2 winner -> affected = {Carl, Dana}, window starts Jun 1
        client.put(f"/matches/{m3['id']}", json={"player1_score": 3, "player2_score": 0})

        matches = client.get("/matches/").json()
        assert len(matches) == 3

        # Bob is a non-affected in-window player: he must enter at his
        # pre-window rating (1216 from the Jan 5 match), not at start_elo.
        m2 = next(m for m in matches if m["date"] == "2025-06-01")
        assert m2["elo_before_a"] == pytest.approx(1216.0, abs=1e-9)

        # Every stored snapshot equals the manual full-history replay.
        self._assert_equals_full_replay(client)

    def test_stale_rating_after_only_match_deleted(self, client, db_session):
        """A player whose only match is deleted is reset to start_elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        b = _create_player(db_session, "Bob", elo=1200)
        c = _create_player(db_session, "Cara", elo=1200)
        a = _create_player(db_session, "Ada", elo=1200)

        # Jan 5: Bob beats Cara
        _create_match_api(client, b.id, c.id, b.id, "2025-01-05")
        # Jun 1: Ada beats Bob (Ada's ONLY match)
        m2 = _create_match_api(client, a.id, b.id, a.id, "2025-06-01").json()

        # Delete Ada's only match
        client.delete(f"/matches/{m2['id']}")

        # Ada is reset to the initial state (stale-rating edge case).
        db_session.expire_all()
        player_a = db_session.query(Player).filter(Player.id == a.id).first()
        assert player_a.current_elo == 1200.0
        assert player_a.last_match_date is None
        assert player_a.active is False

        # Bob keeps a recalculated rating from his remaining match.
        assert _get_player_elo(client, b.id) == pytest.approx(1216.0, abs=1e-9)

    def test_affected_players_still_use_start_elo(self, client, db_session):
        """Directly affected players enter the recalc window at start_elo."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1200)

        # Jan 5: Bob beats Alice
        m1 = _create_match_api(client, a.id, b.id, b.id, "2025-01-05").json()

        # Edit the match -> affected = {Alice, Bob}; window = the whole match.
        client.put(f"/matches/{m1['id']}", json={"player1_score": 3, "player2_score": 0})

        after = client.get(f"/matches/{m1['id']}").json()
        # Both entered at start_elo (their whole history is inside the window).
        assert after["elo_before_a"] == pytest.approx(1200.0, abs=1e-9)
        assert after["elo_before_b"] == pytest.approx(1200.0, abs=1e-9)
        assert after["elo_after_a"] == pytest.approx(1216.0, abs=1e-9)
        assert after["elo_after_b"] == pytest.approx(1184.0, abs=1e-9)


class TestBoundedTimeline:
    """Fix #11 - _recalculate_elo_timeline only loads matches from the window.

    The recalculation window is fetched with ``MatchRepository.get_from_match``
    (a bounded query) instead of ``get_all()`` + index-scan + slice. Results must
    be identical to the previous full-table algorithm.
    """

    @staticmethod
    def _expected(ra: float, rb: float) -> float:
        """Standard Elo expected score for rating ra against rb."""
        return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))

    def _assert_equals_full_replay(self, client) -> None:
        """Assert all stored snapshots equal a manual full-history replay.

        Each player begins the from-scratch replay at their real ``start_elo``
        — players do not all start at 1200.
        """
        players = client.get("/players/").json()
        start_ratings = {p["id"]: float(p["start_elo"]) for p in players}
        matches = sorted(
            client.get("/matches/").json(),
            key=lambda m: (m["date"], m["created_at"], m["id"]),
        )
        ratings: dict[int, float] = {}
        for m in matches:
            pa, pb = m["player_a_id"], m["player_b_id"]
            ra = ratings.get(pa, start_ratings[pa])
            rb = ratings.get(pb, start_ratings[pb])
            ea = self._expected(ra, rb)
            aa = 1.0 if m["winner_id"] == pa else 0.0
            ab = 1.0 - aa
            k = 32.0
            na, nb = ra + k * (aa - ea), rb + k * (ab - (1.0 - ea))
            ratings[pa], ratings[pb] = na, nb
            assert m["elo_before_a"] == pytest.approx(ra, abs=1e-9)
            assert m["elo_after_a"] == pytest.approx(na, abs=1e-9)
            assert m["elo_before_b"] == pytest.approx(rb, abs=1e-9)
            assert m["elo_after_b"] == pytest.approx(nb, abs=1e-9)

    def test_equivalence_with_full_replay(self, client, db_session):
        """Window recalc (bounded query, mixed start Elos) equals a full replay."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1400)
        c = _create_player(db_session, "Carl", elo=1500)
        d = _create_player(db_session, "Dana", elo=1100)
        e = _create_player(db_session, "Eve", elo=1600)
        f = _create_player(db_session, "Frank", elo=900)

        # Pre-window history with differing starting ratings.
        _create_match_api(client, a.id, b.id, a.id, "2025-01-05")
        _create_match_api(client, c.id, d.id, c.id, "2025-01-05")
        # Feb 1: Eve vs Frank - their FIRST match, so deleting it opens a
        # MID-window recalculation (the Jan 5 matches stay untouched).
        m2 = _create_match_api(client, e.id, f.id, e.id, "2025-02-01").json()
        # Matches the recalculation must reproduce exactly.
        _create_match_api(client, b.id, e.id, b.id, "2025-03-01")
        _create_match_api(client, a.id, f.id, f.id, "2025-03-02")

        # Delete the Feb match -> affected = {Eve, Frank}; their earliest remaining
        # match is Mar 1, so the window starts MID-history. Every remaining snapshot
        # must equal a from-scratch replay seeded from each player's real start_elo.
        client.delete(f"/matches/{m2['id']}")
        self._assert_equals_full_replay(client)

    def test_different_start_elo_entered_at_real_value(self, client, db_session):
        """Non-default start_elo players enter recalculation at their real value."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pro = _create_player(db_session, "Pro", elo=1500)
        rook = _create_player(db_session, "Rookie", elo=1000)

        m1 = _create_match_api(client, pro.id, rook.id, pro.id, "2025-01-05").json()
        # Edit -> affected = {Pro, Rookie}. They must enter the recalculation at
        # their REAL start_elo (1500 and 1000), NOT at a hardcoded 1200.
        client.put(f"/matches/{m1['id']}", json={"player1_score": 0, "player2_score": 3})

        after = client.get(f"/matches/{m1['id']}").json()
        assert after["elo_before_a"] == pytest.approx(1500.0, abs=1e-9)
        assert after["elo_before_b"] == pytest.approx(1000.0, abs=1e-9)
        self._assert_equals_full_replay(client)

    def test_slice_equals_get_from_match(self, client, db_session):
        """get_from_match returns the same [id] sequence as get_all()[start_idx:]."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1200)
        _create_match_api(client, a.id, b.id, a.id, "2025-01-05")
        m2 = _create_match_api(client, a.id, b.id, b.id, "2025-01-05").json()  # same day
        _create_match_api(client, a.id, b.id, a.id, "2025-02-01")

        from app.repositories.match import MatchRepository

        db_session.expire_all()
        repo = MatchRepository(db_session)
        earliest = repo.get_by_id(m2["id"])
        assert earliest is not None

        # Old algorithm output: get_all() + linear scan + slice.
        all_matches = repo.get_all()
        start_idx = next(i for i, mm in enumerate(all_matches) if mm.id == earliest.id)
        expected_ids = [m.id for m in all_matches[start_idx:]]

        # New bounded query output.
        actual_ids = [m.id for m in repo.get_from_match(earliest)]
        assert actual_ids == expected_ids

    def test_boundary_respects_same_day_ties(self, client, db_session):
        """A same-day match before the earliest affected match stays out of the window."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1200)
        c = _create_player(db_session, "Carl", elo=1200)
        d = _create_player(db_session, "Dana", elo=1200)

        # Jan 5: A beats B (same-day EARLIER), then C beats D (same-day LATER).
        m1 = _create_match_api(client, a.id, b.id, a.id, "2025-01-05").json()
        m2 = _create_match_api(client, c.id, d.id, c.id, "2025-01-05").json()
        _create_match_api(client, a.id, c.id, c.id, "2025-01-07")

        # Edit m2 (C vs D) -> affected = {C, D}; window starts at m2, which sits
        # on the SAME DAY as m1 (A vs B) but strictly AFTER it. m1 must NOT be
        # pulled into the recalculation window: its snapshots must stay untouched.
        # (If m1 were wrongly included, A/B would be boundary-initialised from m1
        # itself and its stored snapshots would be recomputed to different values.)
        client.put(f"/matches/{m2['id']}", json={"player1_score": 0, "player2_score": 3})

        m1_after = client.get(f"/matches/{m1['id']}").json()
        assert m1_after["elo_after_a"] == pytest.approx(1216.0, abs=1e-9)
        assert m1_after["elo_after_b"] == pytest.approx(1184.0, abs=1e-9)

        # Affected players (C, D) have no pre-window history, so the window result
        # is byte-identical to a full-history replay across all remaining matches.
        self._assert_equals_full_replay(client)

    def test_earliest_match_is_first_returned(self, client, db_session):
        """get_from_match includes earliest_match itself (inclusive boundary)."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        a = _create_player(db_session, "Alice", elo=1200)
        b = _create_player(db_session, "Bob", elo=1200)
        _create_match_api(client, a.id, b.id, a.id, "2025-01-05")
        m2 = _create_match_api(client, b.id, a.id, b.id, "2025-01-06").json()
        m3 = _create_match_api(client, a.id, b.id, a.id, "2025-01-07").json()

        from app.repositories.match import MatchRepository

        db_session.expire_all()
        repo = MatchRepository(db_session)
        earliest = repo.get_by_id(m2["id"])
        assert earliest is not None

        rows = repo.get_from_match(earliest)
        assert [m.id for m in rows] == [m2["id"], m3["id"]]
class TestDisabledPlayerRecalculation:
    """Disabled players must stay inactive when recalculation touches their timeline."""

    def test_match_edit_does_not_reactivate_disabled_player(self, client, db_session):
        """A timeline recalculation triggered by a match edit keeps disabled players inactive."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        pa = _create_player(db_session, "Alice", elo=1200)
        pb = _create_player(db_session, "Bob", elo=1200)

        resp = _create_match_api(client, pa.id, pb.id, pa.id, "2025-06-01")
        assert resp.status_code == 201
        m_id = resp.json()["id"]

        # Disable Alice directly in the DB (as an admin would in the UI)
        db_session.query(Player).filter(Player.id == pa.id).update({
            "disabled": True,
            "active": False,
        })
        db_session.commit()

        # Editing the match triggers a timeline recalculation that includes Alice
        resp = client.put(f"/matches/{m_id}", json={"player_a_180s": 1})
        assert resp.status_code == 200

        db_session.expire_all()
        alice = db_session.query(Player).filter(Player.id == pa.id).first()
        bob = db_session.query(Player).filter(Player.id == pb.id).first()
        assert alice.disabled is True
        assert alice.active is False
        assert bob.active is True
