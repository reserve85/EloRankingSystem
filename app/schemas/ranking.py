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
    position_change: int
    total_matches: int = 0

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
