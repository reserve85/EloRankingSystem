"""Player schemas for input/output validation."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PlayerCreate(BaseModel):
    """Schema for creating a new player."""

    name: str = Field(..., min_length=1, max_length=200)
    start_elo: Optional[int] = Field(default=None, ge=0)


class PlayerUpdate(BaseModel):
    """Schema for updating a player."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start_elo: Optional[int] = Field(default=None, ge=0)


class PlayerResponse(BaseModel):
    """Schema for player response."""

    id: int
    name: str
    start_elo: int
    current_elo: float
    active: bool
    disabled: bool
    last_match_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}