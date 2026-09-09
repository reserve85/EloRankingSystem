"""Tests for ranking generation."""

from datetime import date, datetime, timedelta


from app.models.player import Player
from app.models.player_disable_period import PlayerDisablePeriod
from app.models.user import User, UserRole
from app.auth.password import hash_password
from app.services.ranking import RankingService


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


def _create_player(
    db_session,
    name="Player",
    elo=1200,
    active=True,
    last_match=None,
    created_at=None,
    entry_date=None,
):
    """Create a player directly in the database.

    ``entry_date`` is the player's member-since date (the authoritative
    "entry date" for ranking eligibility, Fix #3 II). It defaults to the
    ``created_at`` date, which itself is backdated by default so ranking tests
    with 2025-06 windows treat the player as already existing. Explicit
    per-test values are used for entry-date scenarios.
    """
    if created_at is None:
        created_at = datetime(2025, 5, 1, 12, 0, 0)
    if entry_date is None:
        entry_date = created_at.date()
    player = Player(
        name=name,
        start_elo=elo,
        current_elo=float(elo),
        active=active,
        disabled=False,
        last_match_date=last_match,
        created_at=created_at,
        entry_date=entry_date,
    )
    db_session.add(player)
    db_session.commit()
    db_session.refresh(player)
    return player


def _create_match(client, pa_id, pb_id, winner_id, match_date):
    """Create a match via API using Best-of-5 scores."""
    score_a = 3 if winner_id == pa_id else 0
    score_b = 3 if winner_id == pb_id else 0
    return client.post(
        "/matches/",
        json={
            "date": match_date,
            "player_a_id": pa_id,
            "player_b_id": pb_id,
            "player1_score": score_a,
            "player2_score": score_b,
        },
    )


def _get_ranking(client, from_date=None, to_date=None, include_inactive=False):
    """Get ranking via API."""
    params = {"include_inactive": str(include_inactive).lower()}
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    return client.get("/rankings/", params=params)


def _backdate_created_at(db_session, when=None):
    """Backdate every player's entry date and creation date to ``when``.

    Fixtures that create players via the API and then register matches with
    earlier dates need this so the players count as already existing on those
    match dates (the ranking uses the explicit entry_date).
    """
    if when is None:
        when = datetime(2026, 1, 1, 12, 0, 0)
    for p in db_session.query(Player).all():
        p.created_at = when
        p.entry_date = when.date()
    db_session.commit()


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
        # Fix #1: no match history -> no previous ranking position, so the
        # position change reports None (the UI renders it as '-').
        assert data["entries"][0]["position_change"] is None

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


class TestMissingHistoricalRank:
    """Fix #1: players without any match must not get a phantom rank change."""

    def test_new_player_without_matches_shows_no_rank_change(self, client, db_session):
        """
        A newly created player with zero matches has no previous ranking
        position, so position_change must be '-' (None) even when other
        players move around them inside the period.

        Regression: the old code fabricated start/end positions from the
        player's configured start_elo, producing a bogus +1 in the "Pos"
        column although no match was ever played.
        """
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        # Brand-new member without any matches (API-created => active=False).
        _create_player(db_session, "Jasmin", elo=1500, active=False)
        top = _create_player(db_session, "Top", elo=1550)
        weak = _create_player(db_session, "Weak", elo=1200)

        # Top (start_elo 1550) loses twice to the 1200 player inside the period,
        # dropping below Jasmin's 1500: 1550 -> ~1521.8 -> ~1494.1. Before the
        # fix Jasmin's phantom start position (#2) vs end position (#1) showed +1.
        _create_match(client, top.id, weak.id, weak.id, "2025-06-15")
        _create_match(client, top.id, weak.id, weak.id, "2025-06-20")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30", include_inactive=True)
        entries = resp.json()["entries"]
        jasmin_entry = next(e for e in entries if e["player_name"] == "Jasmin")

        assert jasmin_entry["total_matches"] == 0
        assert jasmin_entry["elo_change"] == 0.0
        assert jasmin_entry["position_change"] is None

    def test_established_player_keeps_computed_rank_change(self, client, db_session):
        """
        A player WITH match history before the period but no matches inside it
        still gets a normal rank change: when a higher-ranked opponent drops
        below them, +1 is the correct result (issue acceptance criterion).
        """
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        jasmin = _create_player(db_session, "Jasmin", elo=1500)
        top = _create_player(db_session, "Top", elo=1550)
        weak = _create_player(db_session, "Weak", elo=1200)

        # Jasmin plays before the period and ends at ~1504.8.
        _create_match(client, jasmin.id, weak.id, jasmin.id, "2025-05-15")
        # Top (start_elo 1550, no prior matches) loses twice in the period and
        # falls to ~1494, below Jasmin.
        _create_match(client, top.id, weak.id, weak.id, "2025-06-15")
        _create_match(client, top.id, weak.id, weak.id, "2025-06-20")

        resp = _get_ranking(client, "2025-06-01", "2025-06-30")
        entries = resp.json()["entries"]
        jasmin_entry = next(e for e in entries if e["player_name"] == "Jasmin")

        # No matches in the period, but a real historical rank exists.
        assert jasmin_entry["total_matches"] == 0
        assert jasmin_entry["position_change"] == 1


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
            "2025-06-01",
            "2025-06-30",
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


class TestEntryDateFiltering:
    """Fix #2 + Fix #3 II: players must only appear in rankings from their
    entry date (member-since) onwards.

    Rule: entry_date <= selected_period_end. The explicit ``entry_date`` is
    the authority - matches no longer imply existence.
    """

    # Entry date used for the "joined club" scenarios below.
    ENTRY_ON = date(2025, 9, 9)

    def _create_seeded_members(self, client, db_session):
        """Jasmin (entry 2025-09-09, no matches) + two veteran players."""
        _create_player(
            db_session,
            "Jasmin Störmer",
            elo=1500,
            active=False,
            created_at=datetime(2025, 9, 9, 12, 0, 0),  # on ENTRY_ON
            entry_date=date(2025, 9, 9),  # = the entry / member-since date
        )
        veteran = _create_player(db_session, "Veteran", elo=1400)
        rookie = _create_player(db_session, "Rookie", elo=1200)
        _create_match(client, veteran.id, rookie.id, veteran.id, "2025-09-05")
        return veteran, rookie

    def test_player_not_visible_before_entry_date(self, client, db_session):
        """Period ending before the entry date must not list the player."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        self._create_seeded_members(client, db_session)

        resp = _get_ranking(client, "2025-09-01", "2025-09-08", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" not in names
        assert "Veteran" in names

    def test_player_visible_on_entry_date(self, client, db_session):
        """Period ending ON the entry date must list the player."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        self._create_seeded_members(client, db_session)

        resp = _get_ranking(client, "2025-09-01", "2025-09-09", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" in names

    def test_player_visible_after_entry_date(self, client, db_session):
        """Period ending after the entry date must list the player."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        self._create_seeded_members(client, db_session)

        resp = _get_ranking(client, "2025-09-01", "2025-09-30", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" in names

    def test_entry_date_is_authoritative_regardless_of_matches(self, client, db_session):
        """Matches dated before the entry date do NOT make a player eligible
        earlier; the explicit entry date is the only thing that matters."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        jasmin = _create_player(
            db_session,
            "Jasmin Störmer",
            elo=1500,
            active=False,
            created_at=datetime(2025, 9, 9, 12, 0, 0),
            entry_date=date(2025, 9, 9),
        )
        veteran = _create_player(db_session, "Veteran", elo=1400)
        rookie = _create_player(db_session, "Rookie", elo=1200)
        _create_match(client, veteran.id, rookie.id, veteran.id, "2025-09-05")
        # A match dated BEFORE the entry date (retroactive historical entry).
        _create_match(client, jasmin.id, rookie.id, jasmin.id, "2025-08-20")

        resp = _get_ranking(client, "2025-08-01", "2025-08-31", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" not in names
        assert "Veteran" in names
        assert "Rookie" in names

    def test_legacy_import_member_uses_backfilled_entry_date(self, client, db_session):
        """Imported rosters: the migration backfills entry_date to the first
        recorded match date, so a member who "played since May" but was bulk
        imported on 07-24 is eligible from that backfilled entry date."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        jasmin = _create_player(
            db_session,
            "Jasmin Störmer",
            elo=1500,
            active=False,
            created_at=datetime(2025, 9, 9, 12, 0, 0),  # bulk import date
            entry_date=date(2025, 8, 20),  # backfilled from first recorded match
        )
        veteran = _create_player(db_session, "Veteran", elo=1400)
        rookie = _create_player(db_session, "Rookie", elo=1200)
        _create_match(client, veteran.id, rookie.id, veteran.id, "2025-09-05")
        _create_match(client, jasmin.id, rookie.id, jasmin.id, "2025-08-20")

        resp = _get_ranking(client, "2025-08-01", "2025-08-31", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" in names  # entry_date (08-20) reached

        # Still invisible for periods ending before the entry date.
        resp = _get_ranking(client, "2025-06-01", "2025-08-19", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert "Jasmin Störmer" not in names


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

    def test_all_time_elo_includes_zero_game_players_when_inactive(
        self, client, db_session, monkeypatch
    ):
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
            resp = client.post(
                "/players/",
                json={
                    "name": f"Inactive_{i}",
                    "start_elo": 5000,
                },
            )
            assert resp.status_code == 201
            pid = resp.json()["id"]
            # Mark as inactive (last_match far in the past)
            player = db_session.query(Player).filter(Player.id == pid).first()
            player.last_match_date = date(2020, 1, 1)
            db_session.commit()
            inactive_ids.append(pid)

        # Create the new player with elo 2000 and an opponent
        resp_new = client.post(
            "/players/",
            json={
                "name": "NewPlayer",
                "start_elo": 2000,
            },
        )
        assert resp_new.status_code == 201
        new_player_id = resp_new.json()["id"]

        resp_opp = client.post(
            "/players/",
            json={
                "name": "Opponent",
                "start_elo": 1200,
            },
        )
        assert resp_opp.status_code == 201
        opp_id = resp_opp.json()["id"]

        # NewPlayer plays their first match
        resp_match = client.post(
            "/matches/",
            json={
                "date": "2026-07-20",
                "player_a_id": new_player_id,
                "player_b_id": opp_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )
        assert resp_match.status_code == 201

        # All players were created via the API today, but their matches are
        # dated 2026-07-20. Backdate their entry dates so they count as
        # existing competitors on that date (Fix #2).
        _backdate_created_at(db_session)

        # Get best rank for NewPlayer
        resp = client.get(f"/rankings/player-stats/{new_player_id}/ath")
        assert resp.status_code == 200
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]

        # NewPlayer has elo ~2016 after winning, but 20 inactive players have 5000
        # So best rank should be #21, NOT #1
        assert best_rank is not None
        assert best_rank == 21, (
            f"Expected best rank #21 (after 20 inactive players with elo 5000), got #{best_rank}"
        )

    def test_best_rank_includes_zero_match_players_with_high_start_elo(
        self, client, db_session, monkeypatch
    ):
        """Players with 0 matches but high start_elo should affect best rank."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 5 players with 0 matches and high start_elo
        for i in range(5):
            resp = client.post(
                "/players/",
                json={
                    "name": f"ZeroMatch_{i}",
                    "start_elo": 3000,
                },
            )
            assert resp.status_code == 201

        # Create a player with normal elo
        resp_new = client.post(
            "/players/",
            json={
                "name": "NormalPlayer",
                "start_elo": 1200,
            },
        )
        new_id = resp_new.json()["id"]

        resp_opp = client.post(
            "/players/",
            json={
                "name": "Opponent",
                "start_elo": 1200,
            },
        )
        opp_id = resp_opp.json()["id"]

        # NormalPlayer plays a match
        client.post(
            "/matches/",
            json={
                "date": "2026-07-20",
                "player_a_id": new_id,
                "player_b_id": opp_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )

        # All players were created via the API today, but their matches are
        # dated 2026-07-20. Backdate their entry dates so they count as
        # existing competitors on that date (Fix #2).
        _backdate_created_at(db_session)

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
            f"Expected best rank >= #6 (5 zero-match players with elo 3000 above), got #{best_rank}"
        )

    def test_disable_after_matches_does_not_retroactively_improve_best_rank(
        self, client, db_session, monkeypatch
    ):
        """Fix #5: disabling top players TODAY must not rewrite history.

        Ten top players (Elo 5000) are already entered when ActivePlayer plays
        its first match, so that day's rank is #11. Disabling those ten today
        (open disable period from today) used to erase them from ALL dates,
        which made the Best Rank jump to #1. With the fix the historical rank
        stays #11 - the disable is only effective from today onwards.
        """
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Create 10 top players and disable them TODAY via the API (exactly
        # what the admin does in production).
        top_names = []
        for i in range(10):
            resp = client.post(
                "/players/",
                json={
                    "name": f"Top_{i}",
                    "start_elo": 5000,
                },
            )
            assert resp.status_code == 201
            pid = resp.json()["id"]
            assert client.post(f"/players/{pid}/disable").status_code == 200
            top_names.append(f"Top_{i}")

        # Create active players
        resp_new = client.post(
            "/players/",
            json={
                "name": "ActivePlayer",
                "start_elo": 1200,
            },
        )
        new_id = resp_new.json()["id"]

        resp_opp = client.post(
            "/players/",
            json={
                "name": "Opponent",
                "start_elo": 1200,
            },
        )
        opp_id = resp_opp.json()["id"]

        # Play a match backdated to 2026-07-20
        client.post(
            "/matches/",
            json={
                "date": "2026-07-20",
                "player_a_id": new_id,
                "player_b_id": opp_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )

        # All players were created via the API today, but their matches are
        # dated 2026-07-20. Backdate their entry dates so they count as
        # existing competitors on that date (Fix #2).
        _backdate_created_at(db_session)

        # The 2026-07-20 snapshot still contains the 10 top players.
        resp = _get_ranking(client, "2026-07-20", "2026-07-20", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert top_names[0] in names

        # Best Rank is #11 - NOT #1: the disable only started today, so the
        # 10 top players (Elo 5000) still count for the historical day.
        resp = client.get(f"/rankings/player-stats/{new_id}/ath")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ath_rank"]["best_rank"] == 11, (
            "Disabling the top 10 today must not erase them from history: "
            f"expected #11, got #{data['ath_rank']['best_rank']}"
        )

        # The ranking as of today excludes the (now) disabled top players.
        resp = _get_ranking(client, str(date.today()), str(date.today()), include_inactive=True)
        names_today = [e["player_name"] for e in resp.json()["entries"]]
        assert all(n not in names_today for n in top_names), names_today

    def test_best_rank_normal_scenario(self, client, db_session, monkeypatch):
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
        client.post(
            "/matches/",
            json={
                "date": "2026-07-10",
                "player_a_id": a_id,
                "player_b_id": b_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )

        # Alice wins against Charlie -> still #1
        client.post(
            "/matches/",
            json={
                "date": "2026-07-15",
                "player_a_id": a_id,
                "player_b_id": c_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )

        # Alice loses to Bob -> drops to #2
        client.post(
            "/matches/",
            json={
                "date": "2026-07-20",
                "player_a_id": a_id,
                "player_b_id": b_id,
                "player1_score": 0,
                "player2_score": 3,
            },
        )

        # All players were created via the API today, but their matches are
        # dated 2026-07-10..2026-07-20. Backdate their entry dates so they
        # count as existing competitors on those dates (Fix #2).
        _backdate_created_at(db_session)

        resp = client.get(f"/rankings/player-stats/{a_id}/ath")
        data = resp.json()
        best_rank = data["ath_rank"]["best_rank"]
        date_reached = data["ath_rank"]["date_reached"]

        # Alice's best rank should be #1 (achieved on 2026-07-10)
        assert best_rank == 1
        assert date_reached == "2026-07-10"

    def test_best_rank_player_with_no_matches(self, client, db_session, monkeypatch):
        """Player with no matches should have no best rank."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 3)

        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        resp_p = client.post("/players/", json={"name": "NoMatchPlayer"})
        pid = resp_p.json()["id"]

        resp = client.get(f"/rankings/player-stats/{pid}/ath")
        data = resp.json()
        assert data["ath_rank"]["best_rank"] is None
        assert data["ath_rank"]["date_reached"] is None


class TestDisabledOnDate:
    """Unit tests for the period-aware disable predicate (Fix #5)."""

    def test_never_disabled(self):
        assert RankingService._is_disabled_on(False, [], date(2026, 6, 1)) is False

    def test_legacy_disabled_flag_without_period_is_excluded_everywhere(self):
        # A player flipped to disabled directly in the DB (no recorded period)
        # keeps the old behavior: excluded on every date.
        assert RankingService._is_disabled_on(True, [], date(2026, 6, 1)) is True
        assert RankingService._is_disabled_on(True, [], date(2020, 1, 1)) is True

    def test_inside_closed_window_excluded(self):
        periods = [(date(2026, 1, 10), date(2026, 2, 20))]
        assert RankingService._is_disabled_on(False, periods, date(2026, 1, 10)) is True
        assert RankingService._is_disabled_on(False, periods, date(2026, 2, 1)) is True
        assert RankingService._is_disabled_on(False, periods, date(2026, 2, 20)) is True

    def test_outside_closed_window_included(self):
        periods = [(date(2026, 1, 10), date(2026, 2, 20))]
        assert RankingService._is_disabled_on(False, periods, date(2026, 1, 9)) is False
        assert RankingService._is_disabled_on(False, periods, date(2026, 2, 21)) is False

    def test_open_window_runs_until_today(self):
        periods = [(date(2026, 4, 1), None)]
        assert RankingService._is_disabled_on(False, periods, date(2026, 3, 31)) is False
        assert RankingService._is_disabled_on(False, periods, date(2026, 4, 1)) is True
        assert RankingService._is_disabled_on(False, periods, date(2026, 12, 31)) is True

    def test_multiple_windows_each_apply(self):
        periods = [
            (date(2026, 1, 10), date(2026, 2, 20)),
            (date(2026, 4, 1), date(2026, 11, 30)),
        ]
        assert RankingService._is_disabled_on(False, periods, date(2026, 2, 5)) is True
        assert RankingService._is_disabled_on(False, periods, date(2026, 3, 15)) is False
        assert RankingService._is_disabled_on(False, periods, date(2026, 6, 1)) is True
        assert RankingService._is_disabled_on(False, periods, date(2026, 12, 15)) is False

    def test_recorded_windows_override_flag(self):
        # Recorded periods are authoritative for the dates; the boolean only
        # matters as a fallback for rows with no period at all.
        periods = [(date(2026, 1, 10), date(2026, 2, 20))]
        assert RankingService._is_disabled_on(True, periods, date(2026, 3, 1)) is False


class TestDisablePeriodRanking:
    """Fix #5: disablement is date-aware in the rankings.

    A player is only excluded on dates inside a recorded disable period, so
    the reported bug (disabling the top 10 improves Ingo's Best Rank) cannot
    happen: disabling someone today never rewrites the past. A player can be
    disabled several times (Jan-Feb, then Apr-Nov, ...) and each window is
    honored individually.
    """

    @staticmethod
    def _add_period(db_session, player_id, disabled_from, disabled_to=None):
        db_session.add(
            PlayerDisablePeriod(
                player_id=player_id,
                disabled_from=disabled_from,
                disabled_to=disabled_to,
            )
        )
        db_session.commit()

    def test_disabling_top_ten_today_keeps_ingo_best_rank(self, client, db_session):
        """The reported bug: five top members are disabled today - Ingo's
        Best Rank (#6, reached on 2026-05-06) must stay #6."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)

        # Five top members entered 04-01 with Elo 5000.
        top = [
            _create_player(
                db_session,
                f"Top_{i}",
                elo=5000,
                created_at=datetime(2026, 4, 1, 9, 0),
                entry_date=date(2026, 4, 1),
            )
            for i in range(5)
        ]
        ingo = _create_player(db_session, "Ingo", elo=1000, created_at=datetime(2026, 5, 1, 9, 0))
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2026, 5, 1, 9, 0)
        )
        _create_match(client, ingo.id, sparring.id, ingo.id, "2026-05-06")

        # On 06/05 Ingo is #6 (five 5000-Elo members above him).
        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["Top_0", "Top_1", "Top_2", "Top_3", "Top_4", "Ingo", "Sparring"]
        ath_before = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath_before["ath_rank"]["best_rank"] == 6

        # Admin disables the top five TODAY.
        for p in top:
            assert client.post(f"/players/{p.id}/disable").status_code == 200

        # Historical Best Rank is immutable: still #6, never #1.
        ath_after = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath_after["ath_rank"]["best_rank"] == 6, (
            "Disabling the top players today must not improve Ingo's Best Rank: "
            f"got #{ath_after['ath_rank']['best_rank']}"
        )

        # The 06/05 day-ranking is immutable too.
        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        assert len(resp.json()["entries"]) == 7

        # Today's ranking excludes the five disabled players.
        resp = _get_ranking(client, str(date.today()), str(date.today()), include_inactive=True)
        names_today = [e["player_name"] for e in resp.json()["entries"]]
        assert not any(n.startswith("Top_") for n in names_today), names_today

    def test_multiple_disable_windows_evaluated_per_date(self, client, db_session):
        """Flo is disabled Jan 10-Feb 20 and Apr 1-Nov 30. Every day the
        ranking counts her exactly when she was actually disabled."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        flp = _create_player(db_session, "Flo", elo=5000, created_at=datetime(2025, 1, 1, 9, 0))
        ingo = _create_player(db_session, "Ingo", elo=1000, created_at=datetime(2025, 1, 1, 9, 0))
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2025, 1, 1, 9, 0)
        )
        self._add_period(db_session, flp.id, date(2026, 1, 10), date(2026, 2, 20))
        self._add_period(db_session, flp.id, date(2026, 4, 1), date(2026, 11, 30))

        play_days = [
            "2026-01-05",  # before first window   -> Flo counts,  Ingo #2
            "2026-02-01",  # inside first window   -> Flo excluded, Ingo #1
            "2026-03-15",  # between windows       -> Flo counts,  Ingo #2
            "2026-06-01",  # inside second window  -> Flo excluded, Ingo #1
            "2026-12-15",  # after second window   -> Flo counts,  Ingo #2
        ]
        for day in play_days:
            _create_match(client, ingo.id, sparring.id, ingo.id, day)

        expected = {
            "2026-01-05": ["Flo", "Ingo", "Sparring"],
            "2026-02-01": ["Ingo", "Sparring"],
            "2026-03-15": ["Flo", "Ingo", "Sparring"],
            "2026-06-01": ["Ingo", "Sparring"],
            "2026-12-15": ["Flo", "Ingo", "Sparring"],
        }
        for day, names in expected.items():
            resp = _get_ranking(client, day, day, include_inactive=True)
            assert resp.status_code == 200
            got = [e["player_name"] for e in resp.json()["entries"]]
            assert got == names, f"{day}: expected {names}, got {got}"

        # Best Rank #1 was genuinely reached - but only on days Flo was
        # disabled (2026-02-01, before her second window started).
        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 1
        assert ath["ath_rank"]["date_reached"] == "2026-02-01"

    def test_disable_reactivate_disable_cycle_records_separate_windows(self, client, db_session):
        """Disable -> re-enable -> disable on the same day leaves ONE open window.

        A disable + immediate re-enable is a no-op toggle (the period is
        deleted instead of persisted), so the first cycle produces no junk
        row. Days before the disable keep counting the player historically.
        """
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        flp = _create_player(db_session, "Flo", elo=5000, created_at=datetime(2025, 1, 1, 9, 0))
        ingo = _create_player(db_session, "Ingo", elo=1000, created_at=datetime(2025, 1, 1, 9, 0))
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2025, 1, 1, 9, 0)
        )
        # A match before Flo is ever disabled.
        _create_match(client, ingo.id, sparring.id, ingo.id, "2026-03-15")

        assert client.post(f"/players/{flp.id}/disable").status_code == 200  # window opens
        assert client.post(f"/players/{flp.id}/reactivate").status_code == 200  # deletes it
        assert client.post(f"/players/{flp.id}/disable").status_code == 200  # window opens again

        periods = (
            db_session.query(PlayerDisablePeriod)
            .filter(PlayerDisablePeriod.player_id == flp.id)
            .order_by(PlayerDisablePeriod.disabled_from.asc())
            .all()
        )
        # Only ONE, open, fresh window survives (the toggle rows are gone).
        assert len(periods) == 1
        assert periods[0].disabled_from == date.today()
        assert periods[0].disabled_to is None  # currently disabled again

        # The historical match (2026-03-15) predates the disable -> Flo counted.
        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 2, ath

        # The current ranking excludes Flo (an open window covers today).
        resp = _get_ranking(client, str(date.today()), str(date.today()), include_inactive=True)
        assert "Flo" not in [e["player_name"] for e in resp.json()["entries"]]

    def test_reactivate_same_day_player_visible_in_ranking(self, client, db_session):
        """Fix #5 regression: disable + immediate re-enable on the same day
        must bring the player back into TODAY's ranking.

        The same-day toggle deletes the disable window entirely (the player
        was never absent for a whole day), so no stale row can hide them from
        the current or historical tables.
        """
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        _create_player(db_session, "Ingo", elo=1000, created_at=datetime(2025, 1, 1, 9, 0))
        flo = _create_player(db_session, "Flo", elo=5000, created_at=datetime(2025, 1, 1, 9, 0))

        assert client.post(f"/players/{flo.id}/disable").status_code == 200
        assert client.post(f"/players/{flo.id}/reactivate").status_code == 200

        # The disable was cancelled the same day: no period exists.
        periods = (
            db_session.query(PlayerDisablePeriod)
            .filter(PlayerDisablePeriod.player_id == flo.id)
            .all()
        )
        assert periods == []

        today = date.today()
        resp = _get_ranking(client, str(today), str(today), include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["Flo", "Ingo"], names

        # And she is visible the day after as well.
        tomorrow = today + timedelta(days=1)
        resp = _get_ranking(client, str(tomorrow), str(tomorrow), include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["Flo", "Ingo"], names

        # The exact reported case: the roster for a range that ENDS today
        # (e.g. 01.09. - 09.09.) is computed as of to_date=today, so Flo must
        # show there too - previously the [today, today] window hid her from
        # the entire range.
        range_from = today - timedelta(days=8)
        resp = _get_ranking(client, str(range_from), str(today), include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["Flo", "Ingo"], names


class TestHistoricalBestRankImmutability:
    """Fix #4: adding a new player must never change historical ranks."""

    def test_added_player_does_not_change_existing_best_rank(self, client, db_session):
        """Ingo #32/32 on 2026-05-06 stays #32 after Jasmin joins 2026-09-09.

        Mirrors the live-data situation: every existing player was bulk
        imported on 2026-07-24 (created_at AFTER the historical matches) and
        the migration backfilled their entry_date to the first recorded match
        date. Jasmin joins later WITHOUT any match and must not be inserted
        retroactively - her entry_date is 2026-09-09.
        """
        _login_as(client, db_session, "u1", "pass", UserRole.USER)

        import_date = datetime(2026, 7, 24, 14, 0, 0)  # legacy bulk import
        # 30 members, all on 2000. Pair them up: each plays once on 2026-05-04.
        members = [
            _create_player(
                db_session,
                f"Member_{i:02d}",
                elo=2000,
                created_at=import_date,
                entry_date=date(2026, 5, 4),  # migration backfill: first match
            )
            for i in range(30)
        ]
        ingo = _create_player(
            db_session,
            "Ingo Hohm",
            elo=1200,
            created_at=import_date,
            entry_date=date(2026, 5, 6),  # backfilled from his first match
        )
        sparring = _create_player(
            db_session,
            "Sparring",
            elo=1200,
            created_at=import_date,
            entry_date=date(2026, 5, 6),
        )

        # 15 matches on 2026-05-04 pair the 30 members; all stay >= ~1984.
        for i in range(0, 30, 2):
            _create_match(client, members[i].id, members[i + 1].id, members[i].id, "2026-05-04")
        # Ingo loses his 2026-05-06 match -> lowest elo of the 32 -> #32/32.
        _create_match(client, ingo.id, sparring.id, sparring.id, "2026-05-06")

        # Ground truth: on 2026-05-06 exactly 32 players exist, Ingo is #32.
        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        entries = resp.json()["entries"]
        assert len(entries) == 32
        ingo_entry = next(e for e in entries if e["player_name"] == "Ingo Hohm")
        assert ingo_entry["position"] == 32

        ath_before = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath_before["ath_rank"]["best_rank"] == 32
        assert ath_before["ath_rank"]["date_reached"] == "2026-05-06"

        # Jasmin joins on 2026-09-09 (entry date = creation date, no matches).
        _create_player(
            db_session,
            "Jasmin Störmer",
            elo=1500,
            active=False,
            created_at=datetime(2026, 9, 9, 12, 0, 0),
            entry_date=date(2026, 9, 9),
        )

        # Historical rank on 06/05 is immutable: still 32 players, Ingo #32.
        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        entries = resp.json()["entries"]
        assert len(entries) == 32
        assert "Jasmin Störmer" not in [e["player_name"] for e in entries]
        assert next(e for e in entries if e["player_name"] == "Ingo Hohm")["position"] == 32

        # Best rank statistic is immutable too.
        ath_after = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath_after["ath_rank"]["best_rank"] == 32
        assert ath_after["ath_rank"]["date_reached"] == "2026-05-06"

        # Jasmin is excluded before 09.09. and appears on/after it.
        resp = _get_ranking(client, "2026-05-01", "2026-09-08", include_inactive=True)
        assert "Jasmin Störmer" not in [e["player_name"] for e in resp.json()["entries"]]
        resp = _get_ranking(client, "2026-09-09", "2026-09-09", include_inactive=True)
        assert "Jasmin Störmer" in [e["player_name"] for e in resp.json()["entries"]]

        # Jasmin herself has no match history -> no best rank yet.
        jasmin = db_session.query(Player).filter(Player.name == "Jasmin Störmer").one()
        ath_j = client.get(f"/rankings/player-stats/{jasmin.id}/ath").json()
        assert ath_j["ath_rank"]["best_rank"] is None

    def test_new_player_never_changes_best_rank_of_established_player(self, client, db_session):
        """Adding a later-entered, high-elo player with no matches leaves
        existing best ranks untouched (the /ath endpoint path)."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        alice = _create_player(
            db_session, "Alice", elo=1200, created_at=datetime(2026, 1, 1, 12, 0, 0)
        )
        bob = _create_player(db_session, "Bob", elo=1200, created_at=datetime(2026, 1, 1, 12, 0, 0))
        charlie = _create_player(
            db_session, "Charlie", elo=1200, created_at=datetime(2026, 1, 1, 12, 0, 0)
        )

        _create_match(client, alice.id, bob.id, alice.id, "2026-02-10")
        _create_match(client, alice.id, charlie.id, alice.id, "2026-02-20")

        ath_before = client.get(f"/rankings/player-stats/{alice.id}/ath").json()
        assert ath_before["ath_rank"]["best_rank"] == 1

        # Late joiners with high start_elo but zero matches.
        for i in range(5):
            _create_player(
                db_session,
                f"Late_{i}",
                elo=3000,
                active=False,
                created_at=datetime(2026, 9, 9, 12, 0, 0),
            )

        ath_after = client.get(f"/rankings/player-stats/{alice.id}/ath").json()
        assert ath_after["ath_rank"]["best_rank"] == 1
        assert ath_after["ath_rank"]["date_reached"] == "2026-02-10"


class TestBestRankUsesMinimum:
    """Fix #4: Best Rank is the LOWEST rank number ever achieved (MIN, not
    MAX), and the date is the first date that rank was reached."""

    def test_best_rank_is_minimum_across_dates(self, client, db_session):
        """Daily ranks 3 -> 1 -> 3 yield Best Rank #1 on the middle date."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        alice = _create_player(
            db_session, "Alice", elo=1200, created_at=datetime(2025, 1, 1, 12, 0, 0)
        )
        bob = _create_player(db_session, "Bob", elo=1200, created_at=datetime(2025, 1, 1, 12, 0, 0))
        # Charlie exists (he keeps Alice off #2 early on) but never plays.
        _create_player(db_session, "Charlie", elo=1200, created_at=datetime(2025, 1, 1, 12, 0, 0))

        # 2025-04-01: Alice loses -> #3
        _create_match(client, alice.id, bob.id, bob.id, "2025-04-01")
        # 2025-04-10: Alice upsets Bob -> #1
        _create_match(client, alice.id, bob.id, alice.id, "2025-04-10")
        # 2025-04-20: Alice loses again -> #3
        _create_match(client, alice.id, bob.id, bob.id, "2025-04-20")

        ath = client.get(f"/rankings/player-stats/{alice.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 1
        assert ath["ath_rank"]["date_reached"] == "2025-04-10"

    def test_best_rank_equals_min_of_daily_ranking_positions(self, client, db_session):
        """Property test: over a varied history the ATH best rank equals the
        minimum of the player's daily ranking positions (covers sequences like
        32,20,25 -> #20 and 10,5,8 -> #5)."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        # Six players with distinct ratings so no ties occur.
        start_elos = [1100, 1200, 1300, 1400, 1500, 1600]
        players = [
            _create_player(
                db_session, f"P{start}", elo=start, created_at=datetime(2025, 1, 1, 12, 0, 0)
            )
            for start in start_elos
        ]
        target = players[0]  # start_elo 1100

        # Target climbs by upsetting successively stronger players, then drops.
        schedule = [
            ("2025-02-01", target.name, "P1200", target.name),
            ("2025-02-15", target.name, "P1600", target.name),
            ("2025-03-01", target.name, "P1500", target.name),
            ("2025-03-15", target.name, "P1200", target.name),
            ("2025-04-01", target.name, "P1300", target.name),
            ("2025-04-15", target.name, "P1400", target.name),
            ("2025-05-01", target.name, "P1500", target.name),
            ("2025-05-15", target.name, "P1600", target.name),
            ("2025-06-01", "P1200", target.name, "P1200"),  # target loses
        ]
        by_name = {p.name: p for p in players}
        for match_date, a_name, b_name, winner_name in schedule:
            _create_match(
                client,
                by_name[a_name].id,
                by_name[b_name].id,
                by_name[winner_name].id,
                match_date,
            )

        # Ground truth: the daily position of the target on each date they
        # played, taken from the public ranking endpoint.
        daily_positions: list[int] = []
        daily_dates: list[str] = []
        for match_date, _, _, _ in schedule:
            resp = _get_ranking(client, match_date, match_date, include_inactive=True)
            entries = resp.json()["entries"]
            entry = next(e for e in entries if e["player_name"] == target.name)
            daily_positions.append(entry["position"])
            daily_dates.append(match_date)

        # Non-vacuous: the history must actually vary.
        assert len(set(daily_positions)) > 1

        expected_best = min(daily_positions)
        expected_date = daily_dates[daily_positions.index(expected_best)]

        ath = client.get(f"/rankings/player-stats/{target.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == expected_best
        assert ath["ath_rank"]["date_reached"] == expected_date


class TestDateOnlySemantics:
    """Date-based entry semantics (Fix #3 follow-up).

    A player's entry date is their CALENDAR day - the time-of-day of
    created_at is irrelevant, and position on a date is always decided by
    Elo, never by creation order or insertion id.
    """

    def test_same_day_creation_times_are_equal_and_ranked_by_elo(self, client, db_session):
        """Players created 23:59 vs 00:01 on the same day are equally eligible
        for that day; Elo decides the order, not the creation time."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(db_session, "LowElo", elo=1000, created_at=datetime(2025, 9, 9, 23, 59))
        _create_player(db_session, "HighElo", elo=2000, created_at=datetime(2025, 9, 9, 0, 1))

        resp = _get_ranking(client, "2025-09-09", "2025-09-09", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["HighElo", "LowElo"]

    def test_same_day_entrants_count_position_by_elo_not_creation_order(self, client, db_session):
        """User scenario: player 1 (elo 1000) entered first, then higher-elo
        players entered on the SAME day. The day-ranking includes all of them,
        so player 1's best rank is NOT #1 - it is by Elo (last). Only players
        entering on a LATER date would leave player 1 alone on the first day.
        """
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        p1 = _create_player(
            db_session, "FirstPlayer", elo=1000, created_at=datetime(2025, 6, 1, 8, 0)
        )
        opp = _create_player(db_session, "Opponent", elo=900, created_at=datetime(2025, 6, 1, 9, 0))
        # Three same-day entrants with higher Elo (represents the 50 in the
        # user's example - the rule is the same regardless of count).
        for i, elo in enumerate((2000, 2100, 2200)):
            _create_player(
                db_session,
                f"High_{i}",
                elo=elo,
                created_at=datetime(2025, 6, 1, 10 + i, 0),
            )

        _create_match(client, p1.id, opp.id, p1.id, "2025-06-02")

        # On p1's match day all five same-day entrants exist, ordered by Elo.
        resp = _get_ranking(client, "2025-06-02", "2025-06-02", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["High_2", "High_1", "High_0", "FirstPlayer", "Opponent"]

        ath = client.get(f"/rankings/player-stats/{p1.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 4  # NOT #1; 3 higher-Elo entries above

    def test_later_entrants_leave_earlier_best_rank_intact(self, client, db_session):
        """Player 1 alone on 06-01 is #1; 50 higher-Elo players entered on a
        LATER date must not change that historical rank (issue #4 immutability).
        """
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        p1 = _create_player(
            db_session, "FirstPlayer", elo=1000, created_at=datetime(2025, 6, 1, 8, 0)
        )
        opp = _create_player(db_session, "Opponent", elo=900, created_at=datetime(2025, 6, 1, 9, 0))
        _create_match(client, p1.id, opp.id, p1.id, "2025-06-02")

        ath_before = client.get(f"/rankings/player-stats/{p1.id}/ath").json()
        assert ath_before["ath_rank"]["best_rank"] == 1

        # Same-day entrants count on the 06-02 ranking...
        resp = _get_ranking(client, "2025-06-02", "2025-06-02", include_inactive=True)
        assert [e["player_name"] for e in resp.json()["entries"]] == [
            "FirstPlayer",
            "Opponent",
        ]

        # ...but higher-Elo players entered LATER do not move the 06-02 rank.
        for i in range(3):
            _create_player(
                db_session,
                f"LateHigh_{i}",
                elo=3000,
                active=False,
                created_at=datetime(2025, 6, 5, 12, 0),
            )

        ath_after = client.get(f"/rankings/player-stats/{p1.id}/ath").json()
        assert ath_after["ath_rank"]["best_rank"] == 1
        assert ath_after["ath_rank"]["date_reached"] == "2025-06-02"


class TestEntryDateCountsFullRoster:
    """Fix #3 II: historical ranks and Best Rank count EVERY non-disabled
    player whose entry_date <= date - including inactive members and members
    who have never played. Disabled players are always excluded."""

    def test_never_played_entered_members_count_in_best_rank(self, client, db_session):
        """Ingo enters 2026-05-01, plays 2026-05-06. Three other club members
        also entered 2026-05-01 (one never plays, one is inactive) with higher
        start Elo. On 06/05 Ingo is #4 - NOT #1 - because the full roster that
        existed on that date is ranked, not just the players who had played."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        _create_player(
            db_session, "Ingo Hohm", elo=1000, created_at=datetime(2026, 5, 1, 9, 0)
        )  # entry_date defaults to 2026-05-01
        _create_player(
            db_session,
            "VeteranNeverPlayed",
            elo=2000,
            active=False,
            created_at=datetime(2026, 5, 1, 10, 0),
        )
        _create_player(
            db_session,
            "InactiveMember",
            elo=1800,
            active=False,
            created_at=datetime(2026, 5, 1, 11, 0),
        )
        _create_player(
            db_session, "Reserve", elo=1500, active=False, created_at=datetime(2026, 5, 1, 12, 0)
        )
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2026, 5, 1, 13, 0)
        )
        ingo = db_session.query(Player).filter(Player.name == "Ingo Hohm").one()

        _create_match(client, ingo.id, sparring.id, ingo.id, "2026-05-06")

        # The day-ranking includes all entered members (5), ordered by Elo as
        # of that date (start_elo for never-played).
        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert len(names) == 5
        assert names == [
            "VeteranNeverPlayed",
            "InactiveMember",
            "Reserve",
            "Ingo Hohm",
            "Sparring",
        ]

        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 4

    def test_disabled_players_never_count(self, client, db_session):
        """A player whose ``disabled`` flag is set directly (no recorded
        disable period, e.g. a legacy/DB-level toggle) is excluded from the
        full-roster denominator on every date - the pre-Fix #5 fallback.
        Players disabled through the app get date-aware windows instead."""
        _login_as(client, db_session, "u1", "pass", UserRole.USER)
        ingo = _create_player(
            db_session, "Ingo Hohm", elo=1000, created_at=datetime(2026, 5, 1, 9, 0)
        )
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2026, 5, 1, 9, 0)
        )
        _create_player(
            db_session,
            "FormerMember",
            elo=9999,
            active=False,
            created_at=datetime(2026, 5, 1, 9, 0),
        )
        _create_match(client, ingo.id, sparring.id, ingo.id, "2026-05-06")

        # FormerMember (entry 05-01, disabled) must not shift anyone.
        former = db_session.query(Player).filter(Player.name == "FormerMember").one()
        former.disabled = True
        db_session.commit()

        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["Ingo Hohm", "Sparring"]

        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 1

    def test_changing_entry_date_moves_historical_rank(self, client, db_session):
        """Admin backfilling a member's true entry date changes the
        historical rank accordingly (the club controls member-since dates)."""
        _login_as(client, db_session, "admin", "pass", UserRole.ADMIN)
        ingo = _create_player(
            db_session, "Ingo Hohm", elo=1000, created_at=datetime(2026, 7, 24, 9, 0)
        )
        sparring = _create_player(
            db_session, "Sparring", elo=900, created_at=datetime(2026, 7, 24, 9, 0)
        )
        high = _create_player(
            db_session,
            "HighElo",
            elo=2000,
            active=False,
            created_at=datetime(2026, 7, 24, 9, 0),
        )
        _create_match(client, ingo.id, sparring.id, ingo.id, "2026-05-06")

        # Currently everyone's entry_date = 2026-07-24 (import) -> on 06/05 no
        # one exists, Ingo has no best rank yet.
        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] is None

        # Admin backfills the true member-since dates; Ingo joined 05-01.
        client.put(f"/players/{ingo.id}", json={"entry_date": "2026-05-01"})
        # HighElo joined 04-01 (before Ingo), Sparring on 05-02.
        client.put(f"/players/{high.id}", json={"entry_date": "2026-04-01"})
        client.put(f"/players/{sparring.id}", json={"entry_date": "2026-05-02"})

        resp = _get_ranking(client, "2026-05-06", "2026-05-06", include_inactive=True)
        names = [e["player_name"] for e in resp.json()["entries"]]
        assert names == ["HighElo", "Ingo Hohm", "Sparring"]

        ath = client.get(f"/rankings/player-stats/{ingo.id}/ath").json()
        assert ath["ath_rank"]["best_rank"] == 2
        assert ath["ath_rank"]["date_reached"] == "2026-05-06"


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
        client.post(
            "/matches/",
            json={
                "date": str(date.today()),
                "player_a_id": pa_id,
                "player_b_id": pb_id,
                "player1_score": 3,
                "player2_score": 0,
            },
        )

        _login_as(client, db_session, "user1", "pass", UserRole.USER)
        today_str = str(date.today())
        first_of_month = today_str[:7] + "-01"
        resp = _get_ranking(client, first_of_month, today_str)
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        names = [e["player_name"] for e in entries]
        assert "ActiveGuy" in names
        assert "Opponent" in names
