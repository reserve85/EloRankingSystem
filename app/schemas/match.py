"""Match schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class MatchCreate(BaseModel):
    """Schema for creating a new match."""

    date: date
    player_a_id: int
    player_b_id: int
    winner_id: int

    @model_validator(mode="after")
    def validate_match(self):
        """Validate match creation data."""
        if self.player_a_id == self.player_b_id:
            raise ValueError("Player A and Player B cannot be the same player")
        if self.winner_id not in (self.player_a_id, self.player_b_id):
            raise ValueError("Winner must be either Player A or Player B")
        return self


class MatchUpdate(BaseModel):
    """Schema for updating a match (ADMIN/SYSTEM only)."""

    date: Optional[date] = None
    winner_id: Optional[int] = None


class MatchResponse(BaseModel):
    """Schema for match response."""

    id: int
    date: date
    player_a_id: int
    player_b_id: int
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