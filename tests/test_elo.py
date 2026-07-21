"""Tests for Elo Rating System calculation service."""

import pytest

from app.services.elo import (
    EloResult,
    calculate_expected_score,
    calculate_match_elo,
    calculate_new_rating,
)


class TestExpectedScore:
    """Tests for expected score calculation."""

    def test_equal_ratings_produce_half(self):
        """Two players with equal ratings should have expected score 0.5."""
        result = calculate_expected_score(1200, 1200)
        assert result == pytest.approx(0.5, abs=1e-6)

    def test_higher_rating_higher_expected(self):
        """Player with higher rating should have expected score > 0.5."""
        result = calculate_expected_score(1400, 1200)
        assert result > 0.5

    def test_lower_rating_lower_expected(self):
        """Player with lower rating should have expected score < 0.5."""
        result = calculate_expected_score(1200, 1400)
        assert result < 0.5

    def test_symmetry(self):
        """E(A) + E(B) should equal 1.0."""
        e_a = calculate_expected_score(1300, 1100)
        e_b = calculate_expected_score(1100, 1300)
        assert e_a + e_b == pytest.approx(1.0, abs=1e-10)

    def test_much_higher_rating(self):
        """A much higher rated player should have expected score near 1.0."""
        result = calculate_expected_score(2400, 1200)
        assert result > 0.99

    def test_much_lower_rating(self):
        """A much lower rated player should have expected score near 0.0."""
        result = calculate_expected_score(1200, 2400)
        assert result < 0.01

    def test_200_point_difference(self):
        """A 200-point rating advantage should yield ~0.76 expected score."""
        result = calculate_expected_score(1400, 1200)
        assert result == pytest.approx(0.76, abs=0.01)

    def test_known_values(self):
        """Test against known Elo expected score values."""
        # 1200 vs 1200 -> 0.5
        assert calculate_expected_score(1200, 1200) == pytest.approx(0.5, abs=1e-6)
        # 1600 vs 1400 -> ~0.76
        assert calculate_expected_score(1600, 1400) == pytest.approx(0.76, abs=0.01)
        # 1400 vs 1600 -> ~0.24
        assert calculate_expected_score(1400, 1600) == pytest.approx(0.24, abs=0.01)

    def test_zero_ratings(self):
        """Test with zero ratings (edge case)."""
        result = calculate_expected_score(0, 0)
        assert result == pytest.approx(0.5, abs=1e-6)


class TestCalculateNewRating:
    """Tests for new rating calculation."""

    def test_win_with_favored_expected(self):
        """Winning when expected: small rating gain."""
        # Expected 0.8, actual 1.0, K=32 -> +6.4
        result = calculate_new_rating(1200, 1.0, 0.8, k_factor=32)
        assert result == pytest.approx(1206.4, abs=0.01)

    def test_win_with_unexpected(self):
        """Winning when not expected: larger rating gain."""
        # Expected 0.2, actual 1.0, K=32 -> +25.6
        result = calculate_new_rating(1200, 1.0, 0.2, k_factor=32)
        assert result == pytest.approx(1225.6, abs=0.01)

    def test_loss_with_favored_expected(self):
        """Losing when expected to lose: small rating loss."""
        # Expected 0.2, actual 0.0, K=32 -> -6.4
        result = calculate_new_rating(1200, 0.0, 0.2, k_factor=32)
        assert result == pytest.approx(1193.6, abs=0.01)

    def test_loss_with_unexpected(self):
        """Losing when not expected: larger rating loss."""
        # Expected 0.8, actual 0.0, K=32 -> -25.6
        result = calculate_new_rating(1200, 0.0, 0.8, k_factor=32)
        assert result == pytest.approx(1174.4, abs=0.01)

    def test_rating_changes_sum_to_zero(self):
        """Winner's gain should equal loser's loss (conservation)."""
        k = 32
        expected_a = 0.5
        expected_b = 0.5
        old_a, old_b = 1200, 1200

        new_a = calculate_new_rating(old_a, 1.0, expected_a, k_factor=k)
        new_b = calculate_new_rating(old_b, 0.0, expected_b, k_factor=k)

        gain = new_a - old_a
        loss = old_b - new_b
        assert gain == pytest.approx(loss, abs=1e-10)


class TestCalculateMatchElo:
    """Tests for full match Elo calculation."""

    def test_equal_ratings_player_a_wins(self, monkeypatch):
        """Equal ratings, player A wins."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1200, winner="A")

        assert isinstance(result, EloResult)
        assert result.new_rating_a > 1200
        assert result.new_rating_b < 1200
        assert result.change_a > 0
        assert result.change_b < 0
        assert result.change_a == pytest.approx(-result.change_b, abs=1e-10)
        assert result.expected_a == pytest.approx(0.5, abs=1e-6)
        assert result.expected_b == pytest.approx(0.5, abs=1e-6)

    def test_equal_ratings_player_b_wins(self, monkeypatch):
        """Equal ratings, player B wins."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1200, winner="B")

        assert result.new_rating_a < 1200
        assert result.new_rating_b > 1200
        assert result.change_a < 0
        assert result.change_b > 0

    def test_higher_rated_wins(self, monkeypatch):
        """Higher rated player wins: smaller change."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1400, 1200, winner="A")

        assert result.new_rating_a > 1400
        assert result.new_rating_b < 1200
        # Change should be small since the stronger player won
        assert result.change_a < 16  # Less than half of K

    def test_lower_rated_wins_upset(self, monkeypatch):
        """Lower rated player wins (upset): larger change."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1400, winner="A")

        assert result.new_rating_a > 1200
        assert result.new_rating_b < 1400
        # Change should be larger since the weaker player won
        assert result.change_a > 16  # More than half of K

    def test_rating_conservation(self, monkeypatch):
        """Total rating points should be conserved."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1300, 1100, winner="A")

        total_before = 1300 + 1100
        total_after = result.new_rating_a + result.new_rating_b
        assert total_after == pytest.approx(total_before, abs=1e-10)

    def test_custom_k_factor(self, monkeypatch):
        """Custom K factor should affect the change magnitude."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)

        result_k32 = calculate_match_elo(1200, 1200, winner="A", k_factor=32)
        result_k16 = calculate_match_elo(1200, 1200, winner="A", k_factor=16)

        # K=32 should produce double the change of K=16
        assert result_k32.change_a == pytest.approx(
            result_k16.change_a * 2, abs=1e-10
        )

    def test_default_k_factor_from_config(self, monkeypatch):
        """When no K factor specified, should use config default."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 48)
        result = calculate_match_elo(1200, 1200, winner="A")

        # With K=48, equal ratings, winner gain should be K*(1-0.5) = 24
        assert result.change_a == pytest.approx(24.0, abs=0.01)

    def test_invalid_winner_raises(self, monkeypatch):
        """Invalid winner value should raise ValueError."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        with pytest.raises(ValueError, match="Winner must be 'A' or 'B'"):
            calculate_match_elo(1200, 1200, winner="C")

    def test_invalid_winner_draw_raises(self, monkeypatch):
        """Draw ('D') should raise ValueError."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        with pytest.raises(ValueError, match="Winner must be 'A' or 'B'"):
            calculate_match_elo(1200, 1200, winner="D")

    def test_winner_gains_what_loses_loses(self, monkeypatch):
        """Winner gain must exactly equal loser loss."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1350, 1050, winner="B")
        assert result.change_a == pytest.approx(-result.change_b, abs=1e-10)

    def test_expected_scores_sum_to_one(self, monkeypatch):
        """E(A) + E(B) should equal 1.0."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1300, 1100, winner="A")
        assert result.expected_a + result.expected_b == pytest.approx(1.0, abs=1e-10)


class TestEloResult:
    """Tests for EloResult dataclass."""

    def test_result_fields(self, monkeypatch):
        """Test that EloResult contains all expected fields."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1200, winner="A")

        assert hasattr(result, "new_rating_a")
        assert hasattr(result, "new_rating_b")
        assert hasattr(result, "expected_a")
        assert hasattr(result, "expected_b")
        assert hasattr(result, "change_a")
        assert hasattr(result, "change_b")

    def test_result_values_consistent(self, monkeypatch):
        """Test that change values are consistent with new ratings."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1200, winner="A")

        assert result.new_rating_a == pytest.approx(
            1200 + result.change_a, abs=1e-10
        )
        assert result.new_rating_b == pytest.approx(
            1200 + result.change_b, abs=1e-10
        )


class TestEloEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_high_ratings(self, monkeypatch):
        """Test with very high ratings."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(2800, 2700, winner="A")
        assert result.new_rating_a > 2800
        assert result.new_rating_b < 2700

    def test_very_low_ratings(self, monkeypatch):
        """Test with very low ratings."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(100, 100, winner="A")
        assert result.new_rating_a > 100
        assert result.new_rating_b < 100

    def test_large_rating_gap_upset(self, monkeypatch):
        """Test large upset: 1000 beats 2200."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1000, 2200, winner="A")

        # The upset gain should be very large
        assert result.change_a > 30
        assert result.change_b < -30

    def test_k_factor_zero(self, monkeypatch):
        """K=0 should produce no rating change."""
        monkeypatch.setattr("app.services.elo.settings.k_factor", 32)
        result = calculate_match_elo(1200, 1200, winner="A", k_factor=0)
        assert result.change_a == pytest.approx(0.0, abs=1e-10)
        assert result.change_b == pytest.approx(0.0, abs=1e-10)
        assert result.new_rating_a == pytest.approx(1200.0, abs=1e-10)
        assert result.new_rating_b == pytest.approx(1200.0, abs=1e-10)