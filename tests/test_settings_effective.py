"""Tests for effective settings: k_factor stored per match, default_elo from config, inactivity_months from config."""

from datetime import date, timedelta

import pytest

from app.models.player import Player
from app.models.match import Match
from app.repositories.player import PlayerRepository
from app.schemas.match import MatchCreate, MatchUpdate
from app.schemas.player import PlayerCreate
from app.services.match import MatchService
from app.services.player import PlayerService
from app.services.ranking import RankingService


class TestKFactorStoredPerMatch:
    """Test that k_factor is captured from settings and stored per match."""

    def test_new_match_stores_current_k_factor(self, db_session, monkeypatch):
        """New match should store the current settings.k_factor."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 48)
        monkeypatch.setattr("app.services.match.settings.k_factor", 48)
        monkeypatch.setattr("app.services.match.settings.best_of_legs", 5)

        svc = MatchService(db_session)
        player_repo = PlayerRepository(db_session)
        pa = Player(name="Alice", start_elo=1200, current_elo=1200, active=False, disabled=False)
        pb = Player(name="Bob", start_elo=1200, current_elo=1200, active=False, disabled=False)
        player_repo.create(pa)
        player_repo.create(pb)
        db_session.flush()

        data = MatchCreate(
            date=date.today(), player_a_id=pa.id, player_b_id=pb.id,
            player1_score=3, player2_score=0, best_of_legs=5,
        )
        match = svc.create_match(data)
        assert match.k_factor == 48.0

    def test_two_matches_different_k_factor(self, db_session, monkeypatch):
        """Two matches with different settings.k_factor should each store their own value."""
        monkeypatch.setattr("app.services.match.settings.best_of_legs", 5)

        svc = MatchService(db_session)
        player_repo = PlayerRepository(db_session)
        pa = Player(name="Alice", start_elo=1200, current_elo=1200, active=False, disabled=False)
        pb = Player(name="Bob", start_elo=1200, current_elo=1200, active=False, disabled=False)
        player_repo.create(pa)
        player_repo.create(pb)
        db_session.flush()

        # First match with K=32
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        monkeypatch.setattr("app.services.match.settings.k_factor", 32)
        data1 = MatchCreate(date=date.today() - timedelta(days=1), player_a_id=pa.id, player_b_id=pb.id,
                            player1_score=3, player2_score=0, best_of_legs=5)
        match1 = svc.create_match(data1)
        assert match1.k_factor == 32.0

        # Second match with K=16
        monkeypatch.setattr("app.services.elo.settings.k_factor", 16)
        monkeypatch.setattr("app.services.match.settings.k_factor", 16)
        data2 = MatchCreate(date=date.today(), player_a_id=pb.id, player_b_id=pa.id,
                            player1_score=3, player2_score=0, best_of_legs=5)
        match2 = svc.create_match(data2)
        assert match2.k_factor == 16.0

class TestDeterministicRecalculation:
    """Test that recalculation uses per-match k_factor, not global settings."""

    def test_recalc_uses_match_k_factor_not_global(self, db_session, monkeypatch):
        """After changing global k_factor, recalculation should still use each match's stored k_factor."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        monkeypatch.setattr("app.services.match.settings.k_factor", 32)
        monkeypatch.setattr("app.services.match.settings.best_of_legs", 5)

        svc = MatchService(db_session)
        player_repo = PlayerRepository(db_session)
        pa = Player(name="Alice", start_elo=1200, current_elo=1200, active=False, disabled=False)
        pb = Player(name="Bob", start_elo=1200, current_elo=1200, active=False, disabled=False)
        player_repo.create(pa)
        player_repo.create(pb)
        db_session.flush()

        # Create match with K=32
        data = MatchCreate(date=date.today(), player_a_id=pa.id, player_b_id=pb.id,
                           player1_score=3, player2_score=0, best_of_legs=5)
        match = svc.create_match(data)
        original_change = match.elo_change_a

        # Change global k_factor to 16
        monkeypatch.setattr("app.services.elo.settings.k_factor", 16)
        monkeypatch.setattr("app.services.match.settings.k_factor", 16)

        # Trigger recalculation by re-saving same scores (forces recalc)
        svc.update_match(match.id, MatchUpdate(player1_score=3, player2_score=0, best_of_legs=5))
        db_session.refresh(match)

        # Elo change should still be based on K=32 (stored in match), not K=16
        assert match.elo_change_a == pytest.approx(original_change, abs=1e-10)
        assert match.k_factor == 32.0


class TestConfigDefaultElo:
    """Test that default_elo comes from settings singleton."""

    def test_player_create_uses_config_default_elo(self, db_session, monkeypatch):
        """Player creation should use settings.default_elo when no start_elo provided."""
        monkeypatch.setattr("app.services.player.settings.default_elo", 1500)
        svc = PlayerService(db_session)
        player = svc.create_player(PlayerCreate(name="TestPlayer"))
        assert player.start_elo == 1500
        assert player.current_elo == 1500.0


class TestConfigInactivityMonths:
    """Test that inactivity_months comes from settings singleton."""

    def test_ranking_uses_config_inactivity_months(self, db_session, monkeypatch):
        """Ranking should use settings.inactivity_months for activity cutoff."""
        monkeypatch.setattr("app.services.ranking.settings.inactivity_months", 6)

        player_repo = PlayerRepository(db_session)
        three_months_ago = date.today() - timedelta(days=90)
        p = Player(name="RecentPlayer", start_elo=1200, current_elo=1200,
                   active=True, disabled=False, last_match_date=three_months_ago)
        player_repo.create(p)
        db_session.flush()

        m = Match(
            date=three_months_ago, player_a_id=p.id, player_b_id=p.id,
            winner_id=p.id, loser_id=p.id, best_of_legs=5,
            player1_score=3, player2_score=0,
            elo_before_a=1200, elo_before_b=1200,
            elo_after_a=1200, elo_after_b=1200,
            elo_change_a=0, elo_change_b=0, k_factor=32.0,
        )
        db_session.add(m)
        db_session.commit()

        ranking_svc = RankingService(db_session)
        result = ranking_svc.get_all_players_all_time_high_elo()
        active_players = [r for r in result if not r["inactive"]]
        assert len(active_players) >= 1
