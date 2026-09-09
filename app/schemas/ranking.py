"""Ranking schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class RankingEntry(BaseModel):
    """Single entry in a ranking table."""

    player_id: int
    player_name: str
    position: int
    elo_rating: float
    elo_change: float
    # None when the player has no previous ranking position (no matches up to
    # to_date) - the UI renders it as '-'. (Fix #1)
    position_change: Optional[int] = None
    total_matches: int = 0
    total_180s: int = 0
    high_finishes: list[int] = []
    low_darts: list[int] = []

    model_config = {"from_attributes": True}


class RankingResponse(BaseModel):
    """Response containing ranking data."""

    from_date: date
    to_date: date
    entries: list[RankingEntry]
    generated_at: datetime


class RankingRequest(BaseModel):
    """Request parameters for ranking generation."""

    from_date: Optional[date] = None
    to_date: Optional[date] = None
    include_inactive: bool = False
