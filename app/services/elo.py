"""Elo Rating System calculation service.

Implements the standard Elo formula:
    Expected(A) = 1 / (1 + 10^((RatingB - RatingA) / 400))
    NewRating = OldRating + K * (Actual - Expected)

Only supports Winner/Loser outcomes (no draws).
"""

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class EloResult:
    """Result of an Elo calculation for a single match."""

    new_rating_a: float
    new_rating_b: float
    expected_a: float
    expected_b: float
    change_a: float
    change_b: float


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """Calculate the expected score for player A against player B.

    Uses the standard Elo expected score formula:
        E(A) = 1 / (1 + 10^((Rb - Ra) / 400))

    Args:
        rating_a: Current rating of player A.
        rating_b: Current rating of player B.

    Returns:
        Expected score for player A (between 0 and 1).
    """
    exponent = (rating_b - rating_a) / 400.0
    return 1.0 / (1.0 + 10.0 ** exponent)


def calculate_new_rating(
    current_rating: float,
    actual_score: float,
    expected_score: float,
    k_factor: float | None = None,
) -> float:
    """Calculate a new rating using the Elo formula.

    NewRating = OldRating + K * (Actual - Expected)

    Args:
        current_rating: Player's current rating.
        actual_score: Actual result (1.0 for win, 0.0 for loss).
        expected_score: Expected score from calculate_expected_score().
        k_factor: K-factor override. If None, uses configured default.

    Returns:
        New rating as float.
    """
    if k_factor is None:
        k_factor = float(settings.k_factor)
    return current_rating + k_factor * (actual_score - expected_score)


def calculate_match_elo(
    rating_a: float,
    rating_b: float,
    winner: str,
    k_factor: float | None = None,
) -> EloResult:
    """Calculate new Elo ratings for both players after a match.

    Args:
        rating_a: Current rating of player A.
        rating_b: Current rating of player B.
        winner: Either "A" or "B" indicating the winner.
        k_factor: K-factor override. If None, uses configured default.

    Returns:
        EloResult with new ratings, expected scores, and changes.

    Raises:
        ValueError: If winner is not "A" or "B".
    """
    if winner not in ("A", "B"):
        raise ValueError(f"Winner must be 'A' or 'B', got '{winner}'")

    if k_factor is None:
        k_factor = float(settings.k_factor)

    # Calculate expected scores
    expected_a = calculate_expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a  # E(B) = 1 - E(A)

    # Actual scores: winner gets 1.0, loser gets 0.0
    actual_a = 1.0 if winner == "A" else 0.0
    actual_b = 1.0 - actual_a

    # Calculate new ratings
    new_rating_a = calculate_new_rating(rating_a, actual_a, expected_a, k_factor)
    new_rating_b = calculate_new_rating(rating_b, actual_b, expected_b, k_factor)

    # Calculate changes
    change_a = new_rating_a - rating_a
    change_b = new_rating_b - rating_b

    return EloResult(
        new_rating_a=new_rating_a,
        new_rating_b=new_rating_b,
        expected_a=expected_a,
        expected_b=expected_b,
        change_a=change_a,
        change_b=change_b,
    )