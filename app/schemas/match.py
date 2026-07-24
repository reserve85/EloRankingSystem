"""Match schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings

# Impossible high finishes in 3 darts (cannot be checked out with 3 darts)
IMPOSSIBLE_HIGH_FINISHES = {169, 168, 166, 165, 163, 162, 159}


# Valid best_of_legs values (odd numbers 1-21)
VALID_BEST_OF = {1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21}


def get_valid_scores(best_of: int = 0) -> set[tuple[int, int]]:
    """Generate valid score combinations for a given best_of_legs.

    Args:
        best_of: The best_of_legs value. If 0, uses settings default.

    Returns:
        Set of (score_a, score_b) tuples where one score equals wins_needed.
    """
    if best_of <= 0:
        best_of = settings.best_of_legs
    if best_of % 2 == 0:
        best_of = best_of - 1
    wins_needed = (best_of + 1) // 2

    valid = set()
    for loser_score in range(wins_needed):
        valid.add((wins_needed, loser_score))
        valid.add((loser_score, wins_needed))
    return valid


def determine_winner(score1: int, score2: int, best_of: int = 0) -> int:
    """Determine winner from scores.

    Returns:
        1 if player_a wins, 2 if player_b wins.

    Raises:
        ValueError: If scores are invalid.
    """
    valid = get_valid_scores(best_of)
    if (score1, score2) not in valid:
        if best_of <= 0:
            best_of = settings.best_of_legs
        wins = (best_of + 1) // 2
        raise ValueError(
            f"Invalid score combination {score1}:{score2}. "
            f"Best of {best_of}: first to {wins} wins."
        )
    return 1 if score1 > score2 else 2


class MatchStatisticsCreate(BaseModel):
    """Schema for match statistics on creation."""

    player_a_180s: int = Field(default=0, ge=0, description="Number of 180s for player A")
    player_b_180s: int = Field(default=0, ge=0, description="Number of 180s for player B")
    player_a_high_finishes: list[int] = Field(default_factory=list, description="High finish scores for player A")
    player_b_high_finishes: list[int] = Field(default_factory=list, description="High finish scores for player B")
    player_a_low_darts: list[int] = Field(default_factory=list, description="Low dart counts for player A")
    player_b_low_darts: list[int] = Field(default_factory=list, description="Low dart counts for player B")

    @model_validator(mode="after")
    def validate_statistics(self):
        """Validate statistics values against configured ranges."""
        hf_min = settings.high_finish_min
        hf_max = settings.high_finish_max
        ld_min = settings.low_darts_min
        ld_max = settings.low_darts_max

        for val in self.player_a_high_finishes:
            if val < hf_min or val > hf_max:
                raise ValueError(
                    f"High finish value {val} is outside valid range [{hf_min}, {hf_max}]"
                )
            if val in IMPOSSIBLE_HIGH_FINISHES:
                raise ValueError(
                    f"High finish value {val} is impossible with 3 darts"
                )
        for val in self.player_b_high_finishes:
            if val < hf_min or val > hf_max:
                raise ValueError(
                    f"High finish value {val} is outside valid range [{hf_min}, {hf_max}]"
                )
            if val in IMPOSSIBLE_HIGH_FINISHES:
                raise ValueError(
                    f"High finish value {val} is impossible with 3 darts"
                )
        for val in self.player_a_low_darts:
            if val < ld_min or val > ld_max:
                raise ValueError(
                    f"Low darts value {val} is outside valid range [{ld_min}, {ld_max}]"
                )
        for val in self.player_b_low_darts:
            if val < ld_min or val > ld_max:
                raise ValueError(
                    f"Low darts value {val} is outside valid range [{ld_min}, {ld_max}]"
                )
        return self


class MatchCreate(MatchStatisticsCreate):
    """Schema for creating a new match."""

    date: date
    player_a_id: int
    player_b_id: int
    player1_score: int = Field(..., ge=0, description="Legs won by player A")
    player2_score: int = Field(..., ge=0, description="Legs won by player B")
    best_of_legs: int = Field(default=0, ge=0, description="Best of N legs (0=use default)")

    @model_validator(mode="after")
    def validate_match(self):
        """Validate match creation data."""
        if self.player_a_id == self.player_b_id:
            raise ValueError("Player A and Player B cannot be the same player")

        bol = self.best_of_legs if self.best_of_legs > 0 else settings.best_of_legs
        if bol not in VALID_BEST_OF:
            raise ValueError(f"best_of_legs must be one of {sorted(VALID_BEST_OF)}, got {bol}")

        valid = get_valid_scores(bol)
        if (self.player1_score, self.player2_score) not in valid:
            wins = (bol + 1) // 2
            raise ValueError(
                f"Invalid score combination {self.player1_score}:{self.player2_score}. "
                f"Best of {bol}: first to {wins} wins."
            )

        return self


class MatchStatisticsUpdate(BaseModel):
    """Schema for updating match statistics."""

    player_a_180s: Optional[int] = Field(default=None, ge=0, description="Number of 180s for player A")
    player_b_180s: Optional[int] = Field(default=None, ge=0, description="Number of 180s for player B")
    player_a_high_finishes: Optional[list[int]] = Field(default=None, description="High finish scores for player A")
    player_b_high_finishes: Optional[list[int]] = Field(default=None, description="High finish scores for player B")
    player_a_low_darts: Optional[list[int]] = Field(default=None, description="Low dart counts for player A")
    player_b_low_darts: Optional[list[int]] = Field(default=None, description="Low dart counts for player B")

    @model_validator(mode="after")
    def validate_statistics(self):
        """Validate statistics values against configured ranges."""
        hf_min = settings.high_finish_min
        hf_max = settings.high_finish_max
        ld_min = settings.low_darts_min
        ld_max = settings.low_darts_max

        if self.player_a_high_finishes is not None:
            for val in self.player_a_high_finishes:
                if val < hf_min or val > hf_max:
                    raise ValueError(
                        f"High finish value {val} is outside valid range [{hf_min}, {hf_max}]"
                    )
                if val in IMPOSSIBLE_HIGH_FINISHES:
                    raise ValueError(
                        f"High finish value {val} is impossible with 3 darts"
                    )
        if self.player_b_high_finishes is not None:
            for val in self.player_b_high_finishes:
                if val < hf_min or val > hf_max:
                    raise ValueError(
                        f"High finish value {val} is outside valid range [{hf_min}, {hf_max}]"
                    )
                if val in IMPOSSIBLE_HIGH_FINISHES:
                    raise ValueError(
                        f"High finish value {val} is impossible with 3 darts"
                    )
        if self.player_a_low_darts is not None:
            for val in self.player_a_low_darts:
                if val < ld_min or val > ld_max:
                    raise ValueError(
                        f"Low darts value {val} is outside valid range [{ld_min}, {ld_max}]"
                    )
        if self.player_b_low_darts is not None:
            for val in self.player_b_low_darts:
                if val < ld_min or val > ld_max:
                    raise ValueError(
                        f"Low darts value {val} is outside valid range [{ld_min}, {ld_max}]"
                    )
        return self


class MatchUpdate(MatchStatisticsUpdate):
    """Schema for updating a match (ADMIN/SYSTEM only)."""

    date: Optional[date] = None
    player1_score: Optional[int] = Field(default=None, ge=0)
    player2_score: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_scores(self):
        """Validate score combination if both are provided."""
        if self.player1_score is not None and self.player2_score is not None:
            valid = get_valid_scores()
            if (self.player1_score, self.player2_score) not in valid:
                best_of = settings.best_of_legs
                wins = (best_of + 1) // 2
                raise ValueError(
                    f"Invalid score combination {self.player1_score}:{self.player2_score}. "
                    f"Best of {best_of}: first to {wins} wins."
                )
        elif self.player1_score is not None or self.player2_score is not None:
            raise ValueError("Both player1_score and player2_score must be provided together")
        return self


class MatchResponse(BaseModel):
    """Schema for match response."""

    id: int
    date: date
    player_a_id: int
    player_b_id: int
    best_of_legs: int = 5
    player1_score: Optional[int] = None
    player2_score: Optional[int] = None
    winner_id: int
    loser_id: int
    elo_before_a: float
    elo_before_b: float
    elo_after_a: float
    elo_after_b: float
    elo_change_a: float
    elo_change_b: float
    player_a_180s: int = 0
    player_b_180s: int = 0
    player_a_high_finishes: Optional[list[int]] = None
    player_b_high_finishes: Optional[list[int]] = None
    player_a_low_darts: Optional[list[int]] = None
    player_b_low_darts: Optional[list[int]] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}