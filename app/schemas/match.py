"""Match schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

# Valid Best-of-5 score combinations
VALID_SCORES = {(3, 0), (3, 1), (3, 2), (2, 3), (1, 3), (0, 3)}


def determine_winner(score1: int, score2: int) -> int:
    """Determine winner from scores.

    Returns:
        1 if player_a wins (score1=3), 2 if player_b wins (score2=3).

    Raises:
        ValueError: If scores are invalid.
    """
    if (score1, score2) not in VALID_SCORES:
        raise ValueError(
            f"Invalid score combination {score1}:{score2}. "
            f"Valid scores: 3:0, 3:1, 3:2, 2:3, 1:3, 0:3"
        )
    return 1 if score1 == 3 else 2


class MatchCreate(BaseModel):
    """Schema for creating a new match."""

    date: date
    player_a_id: int
    player_b_id: int
    player1_score: int = Field(..., ge=0, le=5, description="Score of player A (0-3)")
    player2_score: int = Field(..., ge=0, le=5, description="Score of player B (0-3)")

    @model_validator(mode="after")
    def validate_match(self):
        """Validate match creation data."""
        if self.player_a_id == self.player_b_id:
            raise ValueError("Player A and Player B cannot be the same player")

        # Validate scores
        if (self.player1_score, self.player2_score) not in VALID_SCORES:
            valid_str = ", ".join(f"{s[0]}:{s[1]}" for s in sorted(VALID_SCORES))
            raise ValueError(
                f"Invalid score combination {self.player1_score}:{self.player2_score}. "
                f"Valid scores: {valid_str}"
            )

        # Automatically determine winner
        # Winner is the player with score 3
        # This is handled in the service layer

        return self


class MatchUpdate(BaseModel):
    """Schema for updating a match (ADMIN/SYSTEM only)."""

    date: Optional[date] = None
    player1_score: Optional[int] = Field(default=None, ge=0, le=5)
    player2_score: Optional[int] = Field(default=None, ge=0, le=5)

    @model_validator(mode="after")
    def validate_scores(self):
        """Validate score combination if both are provided."""
        if self.player1_score is not None and self.player2_score is not None:
            if (self.player1_score, self.player2_score) not in VALID_SCORES:
                valid_str = ", ".join(f"{s[0]}:{s[1]}" for s in sorted(VALID_SCORES))
                raise ValueError(
                    f"Invalid score combination {self.player1_score}:{self.player2_score}. "
                    f"Valid scores: {valid_str}"
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
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
