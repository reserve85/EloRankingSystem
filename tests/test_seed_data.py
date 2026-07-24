"""Tests for seeded data: 100 players, 500 matches, 3 months duration."""

import pytest
import random
from datetime import date, timedelta

from app.models.player import Player
from app.models.match import Match
from app.services.elo import calculate_match_elo


@pytest.fixture(scope="module")
def seeded_data():
    """Return seed parameters for reference."""
    return {"players": 100, "matches": 500, "start": date(2025, 4, 1), "end": date(2025, 6, 30)}


def _seed_db(db_session):
    """Seed 100 players and 500 matches into the test database."""
    players = []
    for i in range(1, 101):
        p = Player(name=f"Player_{i:03d}", start_elo=1200, current_elo=1200.0,
                    active=False, disabled=False)
        db_session.add(p)
        players.append(p)
    db_session.commit()
    for p in players:
        db_session.refresh(p)

    start_date = date(2025, 4, 1)
    end_date = date(2025, 6, 30)
    days_range = (end_date - start_date).days
    rng = random.Random(42)
    player_elo = {p.id: 1200.0 for p in players}

    for _ in range(500):
        match_date = start_date + timedelta(days=rng.randint(0, days_range))
        a, b = rng.sample(players, 2)
        winner = a if rng.random() < 0.5 else b
        loser = b if winner == a else a
        w_score = 3
        l_score = rng.choice([0, 1, 2])
        if winner == b:
            p1s, p2s = l_score, w_score
        else:
            p1s, p2s = w_score, l_score

        elo_result = calculate_match_elo(player_elo[a.id], player_elo[b.id],
                                          "A" if winner == a else "B")
        m = Match(
            date=match_date, player_a_id=a.id, player_b_id=b.id,
            winner_id=winner.id, loser_id=loser.id,
            player1_score=p1s, player2_score=p2s,
            elo_before_a=player_elo[a.id], elo_before_b=player_elo[b.id],
            elo_after_a=elo_result.new_rating_a, elo_after_b=elo_result.new_rating_b,
            elo_change_a=elo_result.change_a, elo_change_b=elo_result.change_b,
            player_a_180s=rng.randint(0, 3), player_b_180s=rng.randint(0, 3),
            player_a_high_finishes=[], player_b_high_finishes=[],
            player_a_low_darts=[], player_b_low_darts=[],
        )
        db_session.add(m)
        player_elo[a.id] = elo_result.new_rating_a
        player_elo[b.id] = elo_result.new_rating_b

    for p in players:
        p.current_elo = player_elo[p.id]
        p.active = True
        p.last_match_date = end_date

    db_session.commit()
    return players


class TestSeedDataCounts:
    """Verify the correct amount of seed data exists."""

    def test_100_players_seeded(self, db_session):
        """There should be 100 players after seeding."""
        _seed_db(db_session)
        count = db_session.query(Player).count()
        assert count == 100

    def test_500_matches_seeded(self, db_session):
        """There should be 500 matches after seeding."""
        _seed_db(db_session)
        count = db_session.query(Match).count()
        assert count == 500

    def test_players_have_elo_ratings(self, db_session):
        """All players should have current_elo set."""
        _seed_db(db_session)
        players = db_session.query(Player).all()
        for p in players:
            assert p.current_elo is not None
            assert p.current_elo > 0

    def test_matches_span_3_months(self, db_session):
        """Matches should span from April to June 2025."""
        _seed_db(db_session)
        matches = db_session.query(Match).all()
        dates = [m.date for m in matches]
        assert min(dates) >= date(2025, 4, 1)
        assert max(dates) <= date(2025, 6, 30)

    def test_all_players_active(self, db_session):
        """All seeded players should be active."""
        _seed_db(db_session)
        inactive = db_session.query(Player).filter(Player.active.is_(False)).count()
        assert inactive == 0

    def test_matches_have_elo_data(self, db_session):
        """All matches should have Elo before/after values."""
        _seed_db(db_session)
        matches = db_session.query(Match).all()
        for m in matches:
            assert m.elo_before_a is not None
            assert m.elo_before_b is not None
            assert m.elo_after_a is not None
            assert m.elo_after_b is not None

    def test_elo_changes_are_consistent(self, db_session):
        """Elo change should equal after minus before for each player."""
        _seed_db(db_session)
        matches = db_session.query(Match).all()
        for m in matches:
            assert abs((m.elo_after_a - m.elo_before_a) - m.elo_change_a) < 0.01
            assert abs((m.elo_after_b - m.elo_before_b) - m.elo_change_b) < 0.01

    def test_winner_loser_consistent(self, db_session):
        """Every match should have a valid winner and loser."""
        _seed_db(db_session)
        matches = db_session.query(Match).all()
        for m in matches:
            assert m.winner_id in (m.player_a_id, m.player_b_id)
            assert m.loser_id in (m.player_a_id, m.player_b_id)
            assert m.winner_id != m.loser_id

    def test_elo_distribution_spread(self, db_session):
        """Elo ratings should show spread from wins/losses."""
        _seed_db(db_session)
        players = db_session.query(Player).all()
        elos = [p.current_elo for p in players]
        assert max(elos) > 1200
        assert min(elos) < 1200

    def test_unique_player_names(self, db_session):
        """All player names should be unique."""
        _seed_db(db_session)
        players = db_session.query(Player).all()
        names = [p.name for p in players]
        assert len(names) == len(set(names))

    def test_elo_recalculation_consistency(self, db_session):
        """All Elo changes should sum correctly for each player."""
        _seed_db(db_session)
        matches = db_session.query(Match).all()
        players = {p.id: p for p in db_session.query(Player).all()}

        # For each player, sum all elo changes from matches they participated in
        # and verify it matches (current_elo - start_elo)
        from collections import defaultdict
        total_changes = defaultdict(float)
        for m in matches:
            total_changes[m.player_a_id] += m.elo_change_a
            total_changes[m.player_b_id] += m.elo_change_b

        for pid, player in players.items():
            if pid in total_changes:
                expected = player.start_elo + total_changes[pid]
                assert abs(player.current_elo - expected) < 0.01, \
                    f"Player {player.name}: current={player.current_elo}, expected={expected}"
